"""Pemuatan, validasi, konversi kg, dan statistik kualitas dataset permintaan harian."""
from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

import config as cfg

ITEM_DATA_BAWAAN = ("ayam", "lamm", "steak", "koefte")
ALIAS_KOLOM = {
    "date": "tanggal", "tanggal": "tanggal", "tgl": "tanggal",
    "haehnchen": "ayam_porsi", "ayam": "ayam_porsi", "ayam_porsi": "ayam_porsi",
    "lamm": "lamm_porsi", "lamb": "lamm_porsi", "lamm_porsi": "lamm_porsi",
    "steak": "steak_porsi", "steak_porsi": "steak_porsi",
    "koefte": "koefte_porsi", "koefte_porsi": "koefte_porsi",
    "holiday": "is_holiday", "is_holiday": "is_holiday",
    "weekend": "is_weekend", "is_weekend": "is_weekend",
}


def parse_tanggal_Satu(v) -> pd.Timestamp:
    """Parse satu nilai tanggal: YYYY-MM-DD atau format asli Mendeley 'bulan.hari.tahun' (10.4.2013 = 4 Okt 2013)."""
    if pd.isna(v):
        return pd.NaT
    if isinstance(v, pd.Timestamp):
        return v.normalize()
    s = str(v).strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        bln, hr, thn = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return pd.Timestamp(year=thn, month=bln, day=hr)
        except ValueError:
            return pd.NaT
    return pd.to_datetime(s, errors="coerce")


def parse_tanggal_fleksibel(seri: pd.Series) -> pd.Series:
    return pd.to_datetime(seri.map(parse_tanggal_Satu))


def _baca_csv_mentah(file_or_path) -> pd.DataFrame:
    if file_or_path is None:
        file_or_path = cfg.BUNDLED_PERMINTAAN
    if isinstance(file_or_path, (str, Path)):
        p = Path(file_or_path)
        raw = p.read_bytes()
    elif isinstance(file_or_path, bytes):
        raw = file_or_path
    elif hasattr(file_or_path, "getvalue"):
        raw = file_or_path.getvalue()
    elif hasattr(file_or_path, "read"):
        raw = file_or_path.read()
    else:
        raise ValueError("Sumber data permintaan tidak dikenali.")

    teks_awal = raw[:2048].decode("utf-8-sig", errors="ignore")
    baris_pertama = teks_awal.splitlines()[0] if teks_awal else ""
    sep = ";" if baris_pertama.count(";") > baris_pertama.count(",") else ","
    return pd.read_csv(io.BytesIO(raw), sep=sep, encoding="utf-8-sig")


def muat_permintaan(file_or_path=None) -> pd.DataFrame:
    """Muat dataset permintaan harian, standarkan nama kolom, parse tanggal, dan tambah fitur kalender."""
    df_raw = _baca_csv_mentah(file_or_path)
    if df_raw.empty:
        raise ValueError("File permintaan kosong.")

    peta_kol = {}
    for c in df_raw.columns:
        low = str(c).strip().lower()
        if low in ALIAS_KOLOM:
            peta_kol[c] = ALIAS_KOLOM[low]
        elif low.endswith("_porsi"):
            peta_kol[c] = low

    df = df_raw.rename(columns=peta_kol).copy()
    if "tanggal" not in df.columns:
        raise ValueError("Kolom 'tanggal' (atau 'date') tidak ditemukan pada data permintaan.")

    df["tanggal"] = parse_tanggal_fleksibel(df["tanggal"])
    if df["tanggal"].isna().any():
        n_na = int(df["tanggal"].isna().sum())
        raise ValueError(f"Terdapat {n_na} baris dengan format tanggal tidak valid.")

    kol_porsi = [c for c in df.columns if c.endswith("_porsi")]
    if not kol_porsi:
        raise ValueError("Tidak ditemukan kolom permintaan (*_porsi atau HAEHNCHEN/LAMM/STEAK/KOEFTE).")

    for c in kol_porsi:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        if df[c].isna().any():
            raise ValueError(f"Kolom '{c}' memiliki nilai kosong atau bukan angka.")

    if all(f"{it}_porsi" in df.columns for it in ("lamm", "steak", "koefte")):
        df["daging_porsi"] = df["lamm_porsi"] + df["steak_porsi"] + df["koefte_porsi"]

    df = df.sort_values("tanggal").reset_index(drop=True)
    df["hari"] = df["tanggal"].dt.dayofweek
    df["nama_hari"] = df["hari"].map(lambda i: cfg.HARI_ID[int(i)])
    df["bulan"] = df["tanggal"].dt.month
    df["nama_bulan"] = df["bulan"].map(lambda m: cfg.BULAN_ID[int(m) - 1])
    if "is_weekend" in df.columns:
        df["is_weekend"] = pd.to_numeric(df["is_weekend"], errors="coerce").fillna(0).astype(int)
    else:
        df["is_weekend"] = (df["hari"] >= 5).astype(int)
    if "is_holiday" in df.columns:
        df["is_holiday"] = pd.to_numeric(df["is_holiday"], errors="coerce").fillna(0).astype(int)
    else:
        df["is_holiday"] = 0

    kol_utama = ["tanggal"] + [c for c in ("ayam_porsi", "lamm_porsi", "steak_porsi", "koefte_porsi", "daging_porsi") if c in df.columns]
    kol_tambahan = [c for c in kol_porsi if c not in kol_utama]
    kol_meta = ["is_holiday", "is_weekend", "hari", "nama_hari", "bulan", "nama_bulan"]
    return df[kol_utama + kol_tambahan + kol_meta]


def ke_kg(df: pd.DataFrame, gram_per_porsi: dict[str, float] | None = None) -> pd.DataFrame:
    """Konversi kolom *_porsi menjadi *_kg menggunakan asumsi gram per porsi."""
    gmap = dict(cfg.GRAM_PER_PORSI)
    if gram_per_porsi:
        for k, v in gram_per_porsi.items():
            if v is not None and not pd.isna(v) and float(v) > 0:
                gmap[str(k).lower().replace("_porsi", "").replace("_kg", "")] = float(v)

    out = df.copy()
    for c in [col for col in out.columns if col.endswith("_porsi") and col != "daging_porsi"]:
        item = c[:-6]
        gram = float(gmap.get(item, 200.0))
        out[f"{item}_kg"] = out[c] * gram / 1000.0

    if all(f"{it}_kg" in out.columns for it in ("lamm", "steak", "koefte")):
        out["daging_kg"] = out["lamm_kg"] + out["steak_kg"] + out["koefte_kg"]
    if "daging_porsi" not in out.columns and all(f"{it}_porsi" in out.columns for it in ("lamm", "steak", "koefte")):
        out["daging_porsi"] = out["lamm_porsi"] + out["steak_porsi"] + out["koefte_porsi"]
    return out


def laporan_kualitas(df: pd.DataFrame, satuan: str = "porsi") -> dict:
    """Periksa jumlah hari, rentang tanggal, celah tanggal (tanpa imputasi), nilai nol, dan outlier IQR."""
    tgl = pd.to_datetime(df["tanggal"]).sort_values().reset_index(drop=True)
    awal, akhir = tgl.iloc[0], tgl.iloc[-1]
    hari_kalender = int((akhir - awal).days) + 1
    selisih = tgl.diff().dt.days
    celah = []
    for idx in selisih[selisih > 1].index:
        t_sebelum = tgl.iloc[idx - 1]
        t_sesudah = tgl.iloc[idx]
        hilang = int(selisih.iloc[idx]) - 1
        celah.append({
            "Setelah tanggal": t_sebelum.strftime("%Y-%m-%d"),
            "Sampai sebelum": t_sesudah.strftime("%Y-%m-%d"),
            "Hari tidak tercatat": hilang,
            "Catatan": "Kemungkinan restoran tutup (tidak diimputasi)",
        })

    akhiran = f"_{satuan}"
    baris_item = []
    for c in [col for col in df.columns if col.endswith(akhiran)]:
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if s.empty:
            continue
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        batas_bawah, batas_atas = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        n_outlier = int(((s < batas_bawah) | (s > batas_atas)).sum())
        item_kode = c[: -len(akhiran)]
        baris_item.append({
            "Item": cfg.ITEM_LABEL.get(item_kode, item_kode.title()),
            "Kode": item_kode,
            "n": int(len(s)),
            "Rata-rata": float(s.mean()),
            "Simpangan baku": float(s.std(ddof=1)),
            "CV": float(s.std(ddof=1) / s.mean()) if s.mean() > 0 else np.nan,
            "Median": float(s.median()),
            "Q1": q1,
            "Q3": q3,
            "IQR": iqr,
            "Min": float(s.min()),
            "Maks": float(s.max()),
            "Nilai 0": int((s == 0).sum()),
            "Outlier (IQR)": n_outlier,
        })

    return {
        "jumlah_hari": int(len(df)),
        "tanggal_awal": awal.strftime("%Y-%m-%d"),
        "tanggal_akhir": akhir.strftime("%Y-%m-%d"),
        "hari_kalender": hari_kalender,
        "hari_tidak_tercatat": hari_kalender - int(len(df)),
        "jumlah_celah": len(celah),
        "daftar_celah": pd.DataFrame(celah),
        "nilai_kosong": int(df.isna().sum().sum()),
        "ringkasan_item": pd.DataFrame(baris_item),
    }


def indeks_musiman_bulanan(df: pd.DataFrame, kolom: str) -> tuple[pd.DataFrame, dict]:
    """Hitung indeks musiman bulanan setelah koreksi efek hari-dalam-minggu + uji Kruskal-Wallis."""
    d = df[["tanggal", "hari", "bulan", kolom]].dropna().copy()
    rata_hari = d.groupby("hari")[kolom].transform("mean")
    d["rasio_koreksi"] = np.where(rata_hari > 0, d[kolom] / rata_hari, 1.0)
    rata_total_rasio = float(d["rasio_koreksi"].mean()) or 1.0

    baris = []
    for m in range(1, 13):
        g = d[d["bulan"] == m]
        indeks = float(g["rasio_koreksi"].mean() / rata_total_rasio) if len(g) else 1.0
        baris.append({
            "bulan": m,
            "Bulan": cfg.BULAN_ID[m - 1],
            "n_hari": int(len(g)),
            "Rata-rata": float(g[kolom].mean()) if len(g) else np.nan,
            "Indeks Musiman": round(indeks, 4),
        })

    grup = [g["rasio_koreksi"].values for _, g in d.groupby("bulan") if len(g) >= 3]
    if len(grup) >= 2:
        h_stat, p_val = sps.kruskal(*grup)
        n_all = len(d)
        eps2 = max(0.0, float((h_stat - len(grup) + 1) / (n_all - len(grup))))
        uji = {"H": float(h_stat), "p": float(p_val), "k": len(grup), "n": n_all, "eps2": eps2}
    else:
        uji = {}
    return pd.DataFrame(baris), uji


def profil_hari_rasio(df: pd.DataFrame, kolom: str = "daging_porsi") -> np.ndarray:
    """Kembalikan 7 angka rasio rata-rata per hari (Senin..Minggu) dibagi rata-rata keseluruhan (rata-rata rasio = 1)."""
    if kolom not in df.columns:
        kolom = "ayam_porsi"
    per_hari = df.groupby("hari")[kolom].mean().reindex(range(7)).fillna(1.0).values.astype(float)
    rata = float(per_hari.mean()) or 1.0
    return per_hari / rata
