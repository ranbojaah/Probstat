"""Operasi SQLite: inventaris, data historis survival, permintaan harian, pemasok, parameter item, dan pesanan."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

import config as cfg

SKEMA = """
CREATE TABLE IF NOT EXISTS inventaris (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    produk_id INTEGER,
    item TEXT,
    jumlah REAL NOT NULL,
    satuan TEXT NOT NULL,
    lokasi TEXT NOT NULL,
    suhu_c REAL,
    tanggal_diterima TEXT NOT NULL,
    tanggal_kedaluwarsa_aktual TEXT,
    catatan TEXT DEFAULT '',
    dibuat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT, kategori TEXT, lokasi TEXT, suhu_c REAL,
    durasi_hari REAL NOT NULL, kejadian INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS historis_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    nama_file TEXT, diunggah TEXT, baris_awal INTEGER, baris_valid INTEGER, kejadian INTEGER, laporan TEXT
);
CREATE TABLE IF NOT EXISTS permintaan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal TEXT NOT NULL,
    item TEXT NOT NULL,
    jumlah_porsi REAL NOT NULL,
    sumber TEXT DEFAULT 'impor',
    UNIQUE(tanggal, item)
);
CREATE TABLE IF NOT EXISTS pemasok (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    lead_time_rata REAL NOT NULL,
    lead_time_std REAL DEFAULT 0,
    keandalan REAL DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS pemasok_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pemasok_id INTEGER NOT NULL REFERENCES pemasok(id),
    item TEXT NOT NULL,
    harga_per_kg REAL,
    moq_kg REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS parameter_item (
    item TEXT PRIMARY KEY,
    produk_id INTEGER,
    gram_per_porsi REAL NOT NULL,
    tingkat_layanan REAL DEFAULT 0.95,
    biaya_kurang_per_kg REAL,
    biaya_lebih_per_kg REAL,
    mode_permintaan TEXT DEFAULT 'manual',
    mean_manual_kg_hari REAL,
    cv_manual REAL DEFAULT 0.30,
    pakai_profil_hari INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pesanan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal_pesan TEXT NOT NULL,
    tanggal_datang_estimasi TEXT,
    pemasok_id INTEGER REFERENCES pemasok(id),
    item TEXT NOT NULL,
    jumlah_kg REAL NOT NULL,
    status TEXT DEFAULT 'dipesan'
);
CREATE TABLE IF NOT EXISTS faktor_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal_mulai TEXT NOT NULL,
    tanggal_selesai TEXT NOT NULL,
    faktor REAL NOT NULL DEFAULT 1.0,
    keterangan TEXT NOT NULL
);
"""


@contextmanager
def koneksi():
    con = sqlite3.connect(cfg.DB_PATH)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _iso(d) -> str | None:
    if d is None or d is pd.NaT or (not isinstance(d, (date, datetime)) and pd.isna(d)):
        return None
    return d.isoformat() if isinstance(d, (date, datetime)) else str(d)


def init_db() -> None:
    with koneksi() as con:
        con.executescript(SKEMA)
        # Migrasi aman: tambahkan kolom 'item' pada tabel inventaris lama jika belum ada
        kol_inv = [r[1] for r in con.execute("PRAGMA table_info(inventaris)").fetchall()]
        if "item" not in kol_inv:
            con.execute("ALTER TABLE inventaris ADD COLUMN item TEXT")

        # Seed parameter_item bawaan untuk 4 item data Mendeley
        for item_kode, pid in cfg.ITEM_KE_PRODUK_ID.items():
            gram = float(cfg.GRAM_PER_PORSI.get(item_kode, 200.0))
            con.execute(
                "INSERT OR IGNORE INTO parameter_item "
                "(item, produk_id, gram_per_porsi, tingkat_layanan, biaya_kurang_per_kg, biaya_lebih_per_kg, "
                "mode_permintaan, mean_manual_kg_hari, cv_manual, pakai_profil_hari) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item_kode, int(pid), gram, 0.95, 60000.0, 40000.0, "data", None, 0.30, 0),
            )

        # Seed pemasok contoh jika tabel pemasok masih kosong
        n_pem = con.execute("SELECT COUNT(*) FROM pemasok").fetchone()[0]
        if n_pem == 0:
            cur1 = con.execute(
                "INSERT INTO pemasok (nama, lead_time_rata, lead_time_std, keandalan) VALUES (?,?,?,?)",
                ("Pemasok Unggas Segar Nusantara", 1.0, 0.2, 0.96),
            )
            p1 = cur1.lastrowid
            cur2 = con.execute(
                "INSERT INTO pemasok (nama, lead_time_rata, lead_time_std, keandalan) VALUES (?,?,?,?)",
                ("Pemasok Daging Prima (Sapi & Domba)", 1.0, 0.3, 0.94),
            )
            p2 = cur2.lastrowid
            con.execute("INSERT INTO pemasok_item (pemasok_id, item, harga_per_kg, moq_kg) VALUES (?,?,?,?)",
                        (p1, "ayam", 38000.0, 5.0))
            for it, hrg, moq in [("lamm", 145000.0, 5.0), ("steak", 135000.0, 5.0), ("koefte", 95000.0, 5.0)]:
                con.execute("INSERT INTO pemasok_item (pemasok_id, item, harga_per_kg, moq_kg) VALUES (?,?,?,?)",
                            (p2, it, hrg, moq))

        # Impor permintaan bawaan (permintaan_harian_restoran.csv) jika tabel permintaan kosong
        n_perm = con.execute("SELECT COUNT(*) FROM permintaan").fetchone()[0]
        if n_perm == 0 and cfg.BUNDLED_PERMINTAAN.exists():
            from core import permintaan as perm_mod
            df_p = perm_mod.muat_permintaan(cfg.BUNDLED_PERMINTAAN)
            _simpan_df_permintaan_koneksi(con, df_p, sumber="impor")


def _simpan_df_permintaan_koneksi(con: sqlite3.Connection, df: pd.DataFrame, sumber: str = "impor") -> int:
    kol_porsi = [c for c in df.columns if c.endswith("_porsi") and c != "daging_porsi"]
    tgl_str = pd.to_datetime(df["tanggal"]).dt.strftime("%Y-%m-%d")
    baris = []
    item_terimpor = set()
    for c in kol_porsi:
        item = c[:-6]
        item_terimpor.add(item)
        for t, val in zip(tgl_str, df[c]):
            if pd.notna(val):
                baris.append((t, item, float(val), sumber))
    con.executemany(
        "INSERT OR REPLACE INTO permintaan (tanggal, item, jumlah_porsi, sumber) VALUES (?,?,?,?)",
        baris,
    )
    # Jika bahan sebelumnya bermode manual dan kini punya data permintaan, pindahkan otomatis ke mode 'data'
    for item in item_terimpor:
        ada = con.execute("SELECT item FROM parameter_item WHERE item=?", (item,)).fetchone()
        if ada:
            con.execute("UPDATE parameter_item SET mode_permintaan='data' WHERE item=?", (item,))
        else:
            pid = cfg.ITEM_KE_PRODUK_ID.get(item)
            gram = float(cfg.GRAM_PER_PORSI.get(item, 200.0))
            con.execute(
                "INSERT INTO parameter_item (item, produk_id, gram_per_porsi, tingkat_layanan, "
                "biaya_kurang_per_kg, biaya_lebih_per_kg, mode_permintaan, mean_manual_kg_hari, cv_manual, pakai_profil_hari) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item, pid, gram, 0.95, 60000.0, 40000.0, "data", None, 0.30, 0),
            )
    return len(baris)


# ---------- Permintaan & Parameter Item ----------
def simpan_permintaan_df(df: pd.DataFrame, sumber: str = "impor", ganti_semua: bool = False) -> int:
    with koneksi() as con:
        if ganti_semua:
            con.execute("DELETE FROM permintaan")
        return _simpan_df_permintaan_koneksi(con, df, sumber=sumber)


def unggah_permintaan_item(item: str, df_item: pd.DataFrame, gram_per_porsi: float = 200.0,
                           produk_id: int | None = None, sumber: str = "impor") -> int:
    """Unggah data permintaan harian untuk satu bahan (otomatis memindahkan mode_permintaan ke 'data')."""
    item = str(item).strip().lower()
    tgl_str = pd.to_datetime(df_item["tanggal"]).dt.strftime("%Y-%m-%d")
    vals = pd.to_numeric(df_item["jumlah_porsi"], errors="coerce")
    baris = [(t, item, float(v), sumber) for t, v in zip(tgl_str, vals) if pd.notna(v)]
    with koneksi() as con:
        con.executemany(
            "INSERT OR REPLACE INTO permintaan (tanggal, item, jumlah_porsi, sumber) VALUES (?,?,?,?)",
            baris,
        )
        ada = con.execute("SELECT item FROM parameter_item WHERE item=?", (item,)).fetchone()
        if ada:
            con.execute("UPDATE parameter_item SET mode_permintaan='data' WHERE item=?", (item,))
        else:
            con.execute(
                "INSERT INTO parameter_item (item, produk_id, gram_per_porsi, tingkat_layanan, "
                "biaya_kurang_per_kg, biaya_lebih_per_kg, mode_permintaan, mean_manual_kg_hari, cv_manual, pakai_profil_hari) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item, produk_id, float(gram_per_porsi), 0.95, 60000.0, 40000.0, "data", None, 0.30, 0),
            )
    return len(baris)


def muat_permintaan_db() -> pd.DataFrame:
    """Muat tabel permintaan dari SQLite dalam bentuk wide DataFrame seperti muat_permintaan()."""
    from core import permintaan as perm_mod
    with koneksi() as con:
        raw = pd.read_sql_query("SELECT tanggal, item, jumlah_porsi FROM permintaan ORDER BY tanggal", con)
    if raw.empty:
        if cfg.BUNDLED_PERMINTAAN.exists():
            return perm_mod.muat_permintaan(cfg.BUNDLED_PERMINTAAN)
        return pd.DataFrame()
    piv = raw.pivot_table(index="tanggal", columns="item", values="jumlah_porsi", aggfunc="first").reset_index()
    piv.columns = ["tanggal" if c == "tanggal" else f"{c}_porsi" for c in piv.columns]
    piv["tanggal"] = pd.to_datetime(piv["tanggal"])
    if all(f"{it}_porsi" in piv.columns for it in ("lamm", "steak", "koefte")):
        piv["daging_porsi"] = piv["lamm_porsi"] + piv["steak_porsi"] + piv["koefte_porsi"]
    piv = piv.sort_values("tanggal").reset_index(drop=True)
    piv["hari"] = piv["tanggal"].dt.dayofweek
    piv["nama_hari"] = piv["hari"].map(lambda i: cfg.HARI_ID[int(i)])
    piv["bulan"] = piv["tanggal"].dt.month
    piv["nama_bulan"] = piv["bulan"].map(lambda m: cfg.BULAN_ID[int(m) - 1])
    piv["is_weekend"] = (piv["hari"] >= 5).astype(int)
    # Gabungkan is_holiday dari file bawaan bila tanggal cocok
    if cfg.BUNDLED_PERMINTAAN.exists():
        bawaan = pd.read_csv(cfg.BUNDLED_PERMINTAAN, usecols=["tanggal", "is_holiday"])
        bawaan["tanggal"] = pd.to_datetime(bawaan["tanggal"])
        piv = piv.merge(bawaan, on="tanggal", how="left")
        piv["is_holiday"] = piv["is_holiday"].fillna(0).astype(int)
    else:
        piv["is_holiday"] = 0
    return piv


def daftar_parameter_item() -> pd.DataFrame:
    with koneksi() as con:
        df = pd.read_sql_query("SELECT * FROM parameter_item ORDER BY item", con)
    return df


def get_parameter_item(item: str) -> dict | None:
    with koneksi() as con:
        r = con.execute("SELECT * FROM parameter_item WHERE item=?", (str(item).lower(),)).fetchone()
        if not r:
            return None
        kol = [d[1] for d in con.execute("PRAGMA table_info(parameter_item)").fetchall()]
    return dict(zip(kol, r))


def simpan_parameter_item(item: str, produk_id: int | None, gram_per_porsi: float = 200.0,
                          tingkat_layanan: float = 0.95, biaya_kurang_per_kg: float = 60000.0,
                          biaya_lebih_per_kg: float = 40000.0, mode_permintaan: str = "manual",
                          mean_manual_kg_hari: float | None = 4.0, cv_manual: float = 0.30,
                          pakai_profil_hari: int = 0) -> None:
    item = str(item).strip().lower()
    with koneksi() as con:
        con.execute(
            "INSERT OR REPLACE INTO parameter_item "
            "(item, produk_id, gram_per_porsi, tingkat_layanan, biaya_kurang_per_kg, biaya_lebih_per_kg, "
            "mode_permintaan, mean_manual_kg_hari, cv_manual, pakai_profil_hari) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (item, int(produk_id) if produk_id is not None and not pd.isna(produk_id) else None,
             float(gram_per_porsi), float(tingkat_layanan), float(biaya_kurang_per_kg), float(biaya_lebih_per_kg),
             mode_permintaan, float(mean_manual_kg_hari) if mean_manual_kg_hari is not None else None,
             float(cv_manual), int(bool(pakai_profil_hari))),
        )


def hapus_parameter_item(item: str) -> None:
    with koneksi() as con:
        con.execute("DELETE FROM parameter_item WHERE item=?", (str(item).lower(),))


def peta_gram_per_porsi() -> dict[str, float]:
    df = daftar_parameter_item()
    g = dict(cfg.GRAM_PER_PORSI)
    for _, r in df.iterrows():
        if pd.notna(r["gram_per_porsi"]) and float(r["gram_per_porsi"]) > 0:
            g[str(r["item"])] = float(r["gram_per_porsi"])
    return g


def peta_item_ke_produk_id() -> dict[str, int]:
    df = daftar_parameter_item()
    p = dict(cfg.ITEM_KE_PRODUK_ID)
    for _, r in df.iterrows():
        if pd.notna(r["produk_id"]):
            p[str(r["item"])] = int(r["produk_id"])
    return p


# ---------- Pemasok & Pesanan ----------
def daftar_pemasok() -> pd.DataFrame:
    with koneksi() as con:
        return pd.read_sql_query("SELECT * FROM pemasok ORDER BY id", con)


def daftar_pemasok_item() -> pd.DataFrame:
    with koneksi() as con:
        return pd.read_sql_query(
            "SELECT pi.id, pi.pemasok_id, p.nama AS nama_pemasok, pi.item, pi.harga_per_kg, pi.moq_kg, "
            "p.lead_time_rata, p.lead_time_std, p.keandalan "
            "FROM pemasok_item pi JOIN pemasok p ON pi.pemasok_id = p.id ORDER BY pi.item, pi.id",
            con,
        )


def info_pemasok_untuk_item(item: str) -> dict:
    df = daftar_pemasok_item()
    sub = df[df["item"] == str(item).lower()]
    if sub.empty:
        return {"pemasok_id": None, "nama_pemasok": "Pemasok Default", "lead_time_rata": cfg.LEAD_TIME_DEFAULT,
                "lead_time_std": 0.0, "keandalan": 1.0, "harga_per_kg": 45000.0, "moq_kg": 0.0}
    r = sub.iloc[0]
    return {
        "pemasok_id": int(r["pemasok_id"]),
        "nama_pemasok": str(r["nama_pemasok"]),
        "lead_time_rata": float(r["lead_time_rata"]),
        "lead_time_std": float(r["lead_time_std"] or 0.0),
        "keandalan": float(r["keandalan"] or 1.0),
        "harga_per_kg": float(r["harga_per_kg"] or 0.0),
        "moq_kg": float(r["moq_kg"] or 0.0),
    }


def tambah_pemasok(nama: str, lead_time_rata: float, lead_time_std: float = 0.0, keandalan: float = 1.0) -> int:
    with koneksi() as con:
        cur = con.execute(
            "INSERT INTO pemasok (nama, lead_time_rata, lead_time_std, keandalan) VALUES (?,?,?,?)",
            (nama.strip(), float(lead_time_rata), float(lead_time_std), float(keandalan)),
        )
        return cur.lastrowid


def ubah_pemasok(id_: int, nama: str, lead_time_rata: float, lead_time_std: float = 0.0, keandalan: float = 1.0) -> None:
    with koneksi() as con:
        con.execute(
            "UPDATE pemasok SET nama=?, lead_time_rata=?, lead_time_std=?, keandalan=? WHERE id=?",
            (nama.strip(), float(lead_time_rata), float(lead_time_std), float(keandalan), int(id_)),
        )


def hapus_pemasok(id_: int) -> None:
    with koneksi() as con:
        con.execute("DELETE FROM pemasok_item WHERE pemasok_id=?", (int(id_),))
        con.execute("DELETE FROM pemasok WHERE id=?", (int(id_),))


def simpan_pemasok_item(pemasok_id: int, item: str, harga_per_kg: float, moq_kg: float = 0.0) -> int:
    item = str(item).strip().lower()
    with koneksi() as con:
        ada = con.execute("SELECT id FROM pemasok_item WHERE pemasok_id=? AND item=?", (int(pemasok_id), item)).fetchone()
        if ada:
            con.execute("UPDATE pemasok_item SET harga_per_kg=?, moq_kg=? WHERE id=?",
                        (float(harga_per_kg), float(moq_kg), int(ada[0])))
            return int(ada[0])
        cur = con.execute(
            "INSERT INTO pemasok_item (pemasok_id, item, harga_per_kg, moq_kg) VALUES (?,?,?,?)",
            (int(pemasok_id), item, float(harga_per_kg), float(moq_kg)),
        )
        return cur.lastrowid


def hapus_pemasok_item(id_: int) -> None:
    with koneksi() as con:
        con.execute("DELETE FROM pemasok_item WHERE id=?", (int(id_),))


def daftar_pesanan(status: str | None = None) -> pd.DataFrame:
    with koneksi() as con:
        q = ("SELECT ps.id, ps.tanggal_pesan, ps.tanggal_datang_estimasi, ps.pemasok_id, "
             "COALESCE(p.nama, '-') AS nama_pemasok, ps.item, ps.jumlah_kg, ps.status "
             "FROM pesanan ps LEFT JOIN pemasok p ON ps.pemasok_id = p.id")
        if status:
            return pd.read_sql_query(q + " WHERE ps.status=? ORDER BY ps.id DESC", con, params=(status,))
        return pd.read_sql_query(q + " ORDER BY ps.id DESC", con)


def buat_pesanan(item: str, jumlah_kg: float, pemasok_id: int | None = None,
                 tgl_pesan=None, tgl_datang_estimasi=None) -> int:
    tgl_p = _iso(tgl_pesan or date.today())
    tgl_d = _iso(tgl_datang_estimasi or date.today())
    with koneksi() as con:
        cur = con.execute(
            "INSERT INTO pesanan (tanggal_pesan, tanggal_datang_estimasi, pemasok_id, item, jumlah_kg, status) "
            "VALUES (?,?,?,?,?,?)",
            (tgl_p, tgl_d, pemasok_id, str(item).lower(), float(jumlah_kg), "dipesan"),
        )
        return cur.lastrowid


def terima_pesanan(pesanan_id: int, lokasi: str = "Kulkas", suhu_c: float = 4.0) -> int | None:
    """Ubah status pesanan menjadi 'diterima' dan otomatis tambahkan batch baru ke tabel inventaris."""
    with koneksi() as con:
        r = con.execute("SELECT item, jumlah_kg, status FROM pesanan WHERE id=?", (int(pesanan_id),)).fetchone()
        if not r or r[2] != "dipesan":
            return None
        item, jml, _ = r
        con.execute("UPDATE pesanan SET status='diterima' WHERE id=?", (int(pesanan_id),))
    peta_pid = peta_item_ke_produk_id()
    pid = peta_pid.get(item)
    nama = cfg.ITEM_LABEL.get(item, str(item).title()).split(" (")[0]
    return tambah_bahan(nama, pid, float(jml), "kg", lokasi, suhu_c, date.today(), None,
                        f"Diterima dari pesanan #{pesanan_id}", item=item)


def batalkan_pesanan(pesanan_id: int) -> None:
    with koneksi() as con:
        con.execute("UPDATE pesanan SET status='batal' WHERE id=?", (int(pesanan_id),))


# ---------- Faktor Event Manual ----------
def daftar_faktor_event() -> pd.DataFrame:
    with koneksi() as con:
        return pd.read_sql_query("SELECT * FROM faktor_event ORDER BY tanggal_mulai", con)


def tambah_faktor_event(tgl_mulai, tgl_selesai, faktor: float, keterangan: str) -> int:
    with koneksi() as con:
        cur = con.execute(
            "INSERT INTO faktor_event (tanggal_mulai, tanggal_selesai, faktor, keterangan) VALUES (?,?,?,?)",
            (_iso(tgl_mulai), _iso(tgl_selesai), float(faktor), keterangan.strip()),
        )
        return cur.lastrowid


def hapus_faktor_event(id_: int) -> None:
    with koneksi() as con:
        con.execute("DELETE FROM faktor_event WHERE id=?", (int(id_),))


# ---------- Inventaris ----------
KOLOM_INV = ["id", "nama", "produk_id", "item", "jumlah", "satuan", "lokasi", "suhu_c", "tanggal_diterima",
             "tanggal_kedaluwarsa_aktual", "catatan"]


def daftar_inventaris() -> pd.DataFrame:
    with koneksi() as con:
        return pd.read_sql_query(f"SELECT {', '.join(KOLOM_INV)} FROM inventaris ORDER BY id", con)


def _tebak_item_dari_produk(produk_id: int | None, item: str | None = None) -> str | None:
    if item:
        return str(item).strip().lower()
    if produk_id is None or pd.isna(produk_id):
        return None
    for k, pid in peta_item_ke_produk_id().items():
        if int(pid) == int(produk_id):
            return k
    return None


def tambah_bahan(nama, produk_id, jumlah, satuan, lokasi, suhu_c, tgl_diterima, tgl_kedaluwarsa=None,
                 catatan="", item: str | None = None) -> int:
    item_final = _tebak_item_dari_produk(produk_id, item)
    with koneksi() as con:
        cur = con.execute(
            "INSERT INTO inventaris (nama, produk_id, item, jumlah, satuan, lokasi, suhu_c, tanggal_diterima, "
            "tanggal_kedaluwarsa_aktual, catatan, dibuat) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (nama, produk_id, item_final, jumlah, satuan, lokasi, suhu_c, _iso(tgl_diterima), _iso(tgl_kedaluwarsa),
             catatan or "", datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid


def ubah_bahan(id_, nama, produk_id, jumlah, satuan, lokasi, suhu_c, tgl_diterima, tgl_kedaluwarsa=None,
               catatan="", item: str | None = None) -> None:
    item_final = _tebak_item_dari_produk(produk_id, item)
    with koneksi() as con:
        con.execute(
            "UPDATE inventaris SET nama=?, produk_id=?, item=?, jumlah=?, satuan=?, lokasi=?, suhu_c=?, "
            "tanggal_diterima=?, tanggal_kedaluwarsa_aktual=?, catatan=? WHERE id=?",
            (nama, produk_id, item_final, jumlah, satuan, lokasi, suhu_c, _iso(tgl_diterima), _iso(tgl_kedaluwarsa),
             catatan or "", int(id_)))


def hapus_bahan(id_) -> None:
    with koneksi() as con:
        con.execute("DELETE FROM inventaris WHERE id=?", (int(id_),))


def hapus_semua_bahan() -> None:
    with koneksi() as con:
        con.execute("DELETE FROM inventaris")


def stok_dan_pipeline_kg(item: str, lokasi: str | None = "Kulkas") -> tuple[float, float]:
    """Hitung total stok aktif (kg) dan pesanan dalam perjalanan (kg) untuk suatu item."""
    item = str(item).lower()
    inv = daftar_inventaris()
    if not inv.empty:
        m = inv["item"].fillna("").str.lower() == item
        if lokasi:
            m = m & (inv["lokasi"] == lokasi)
        sub = inv[m]
        # Konversi g -> kg bila ada
        faktor = sub["satuan"].map({"kg": 1.0, "g": 0.001, "porsi": peta_gram_per_porsi().get(item, 200.0) / 1000.0}).fillna(1.0)
        stok_kg = float((sub["jumlah"] * faktor).sum())
    else:
        stok_kg = 0.0
    pes = daftar_pesanan(status="dipesan")
    if not pes.empty:
        pipe_kg = float(pes[pes["item"].str.lower() == item]["jumlah_kg"].sum())
    else:
        pipe_kg = 0.0
    return stok_kg, pipe_kg


# ---------- Data historis ----------
def simpan_historis(df: pd.DataFrame, nama_file: str, baris_awal: int, laporan: str) -> None:
    """Ganti data historis aktif dengan data baru (satu dataset aktif)."""
    with koneksi() as con:
        con.execute("DELETE FROM historis")
        df[["nama", "kategori", "lokasi", "suhu_c", "durasi_hari", "kejadian"]].to_sql(
            "historis", con, if_exists="append", index=False)
        con.execute("DELETE FROM historis_meta")
        con.execute("INSERT INTO historis_meta VALUES (1,?,?,?,?,?,?)",
                    (nama_file, datetime.now().isoformat(timespec="seconds"), baris_awal, len(df),
                     int(df["kejadian"].sum()), laporan))


def muat_historis() -> pd.DataFrame:
    with koneksi() as con:
        return pd.read_sql_query(
            "SELECT nama, kategori, lokasi, suhu_c, durasi_hari, kejadian FROM historis", con)


def meta_historis() -> dict | None:
    with koneksi() as con:
        r = con.execute("SELECT nama_file, diunggah, baris_awal, baris_valid, kejadian, laporan "
                        "FROM historis_meta WHERE id=1").fetchone()
    if not r:
        return None
    return dict(zip(["nama_file", "diunggah", "baris_awal", "baris_valid", "kejadian", "laporan"], r))


def hapus_historis() -> None:
    with koneksi() as con:
        con.execute("DELETE FROM historis")
        con.execute("DELETE FROM historis_meta")


def _perbarui_meta_historis(con: sqlite3.Connection, default_nama: str, tambah_awal: int) -> None:
    n_val, n_kej = con.execute("SELECT COUNT(*), COALESCE(SUM(kejadian), 0) FROM historis").fetchone()
    meta = con.execute("SELECT nama_file, baris_awal FROM historis_meta WHERE id=1").fetchone()
    nama_file = meta[0] if meta and meta[0] else default_nama
    baris_awal = (meta[1] + tambah_awal) if meta and meta[1] is not None else int(n_val)
    con.execute("DELETE FROM historis_meta")
    con.execute(
        "INSERT INTO historis_meta VALUES (1,?,?,?,?,?,?)",
        (nama_file, datetime.now().isoformat(timespec="seconds"), int(baris_awal), int(n_val), int(n_kej), "{}"),
    )


def catat_ke_historis(nama: str, kategori: str, lokasi: str, suhu_c: float | None,
                      durasi_hari: float, kejadian: int) -> None:
    """Tambahkan 1 observasi dari inventaris ke tabel historis dan perbarui meta."""
    durasi = max(float(durasi_hari), 0.5)
    suhu_val = None if suhu_c is None or pd.isna(suhu_c) else float(suhu_c)
    with koneksi() as con:
        con.execute(
            "INSERT INTO historis (nama, kategori, lokasi, suhu_c, durasi_hari, kejadian) VALUES (?,?,?,?,?,?)",
            (nama, kategori, lokasi, suhu_val, durasi, int(kejadian)),
        )
        _perbarui_meta_historis(con, "Catatan Inventaris & Historis", 1)


def gabung_historis(df: pd.DataFrame, default_nama: str = "Data Contoh & Catatan") -> None:
    """Tambahkan baris observasi ke data historis yang sudah ada tanpa menghapus catatan lama."""
    with koneksi() as con:
        df[["nama", "kategori", "lokasi", "suhu_c", "durasi_hari", "kejadian"]].to_sql(
            "historis", con, if_exists="append", index=False)
        _perbarui_meta_historis(con, default_nama, len(df))
