"""Halaman Inventaris Bahan: tabel FEFO, filter, tambah/ubah/hapus, terima pesanan, dan pencatatan Habis/Busuk."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import config as cfg
from core import cache
from core import reference as ref
from database import db
from ui import components as ui
from ui import tables

SEMUA = "Semua kategori"
TANPA_ITEM = "(otomatis dari produk / bahan umum)"


def _peringatan_suhu(lokasi: str, suhu: float) -> str | None:
    if lokasi == "Kulkas" and suhu > 5:
        return "Suhu kulkas sebaiknya 4 °C atau lebih rendah. Suhu ini dapat memperpendek masa simpan sebenarnya."
    if lokasi == "Freezer" and suhu > -15:
        return "Suhu freezer sebaiknya −18 °C atau lebih rendah."
    if lokasi in ("Kulkas", "Freezer") and suhu > 15:
        return "Suhu ini lebih cocok dengan penyimpanan suhu ruang. Periksa kembali lokasi simpan."
    return None


def _form(judul: str, row: dict | None) -> None:
    produk, _, tabel = cache.get_reference()
    mode = "ubah" if row else "tambah"
    k = lambda s: f"{mode}_{s}"  # noqa: E731

    kategori = st.selectbox("Filter kategori produk acuan", [SEMUA] + sorted(produk["kategori"].unique()), key=k("kat"))
    pf = produk if kategori == SEMUA else produk[produk["kategori"] == kategori]
    ids = pf["produk_id"].tolist()
    label = dict(zip(produk["produk_id"], produk["label"]))
    lok_num = (tabel[tabel["jenis"].isin(ref.JENIS_NUMERIK)]
               .groupby("produk_id")["lokasi"].apply(lambda s: ", ".join(s)).to_dict())
    idx = ids.index(int(row["produk_id"])) if row and pd.notna(row.get("produk_id")) and int(row["produk_id"]) in ids else 0
    pid = st.selectbox(
        "Produk acuan (dataset FoodKeeper)", ids, index=idx,
        format_func=lambda i: f"{label[i]}  [acuan hari: {lok_num[i]}]" if i in lok_num else f"{label[i]}  [perlu tgl kemasan]",
        key=k("pid"),
        help="Ketik untuk mencari (bahasa Inggris). Tanda [...] menunjukkan lokasi simpan yang memiliki angka hari di dataset.",
    )
    opsi_item = [TANPA_ITEM] + list(cfg.ITEM_KE_PRODUK_ID.keys())
    item_awal = row.get("item") if (row and row.get("item") in opsi_item) else TANPA_ITEM
    item_pil = st.selectbox("Kaitkan ke item permintaan pengadaan (opsional)", opsi_item,
                            index=opsi_item.index(item_awal), key=k("item"),
                            help="Menghubungkan batch ini dengan perhitungan stok & ROP pada halaman Perencanaan Pengadaan.")
    nama = st.text_input("Nama bahan (opsional, bahasa Indonesia)", value=(row["nama"] or "") if row else "", key=k("nama"),
                         placeholder="Kosongkan untuk memakai nama produk acuan")

    c1, c2 = st.columns(2)
    jumlah = c1.number_input("Jumlah", min_value=0.0, value=float(row["jumlah"]) if row else 5.0, step=0.5, key=k("jml"))
    satuan = c2.selectbox("Satuan", cfg.SATUAN, index=cfg.SATUAN.index(row["satuan"]) if row and row["satuan"] in cfg.SATUAN else 0, key=k("sat"))
    c3, c4 = st.columns(2)
    lokasi_opts = list(cfg.LOKASI)
    lokasi = c3.selectbox("Lokasi penyimpanan", lokasi_opts, index=lokasi_opts.index(row["lokasi"]) if row else 1, key=k("lok"))
    suhu_default = float(row["suhu_c"]) if row and pd.notna(row["suhu_c"]) else {"Suhu Ruang": 27.0, "Kulkas": 4.0, "Freezer": -18.0}[lokasi]
    suhu = c4.number_input("Suhu penyimpanan (°C)", value=suhu_default, step=1.0, key=k(f"suhu_{lokasi}"),
                           help="Dipakai untuk pemeriksaan kewajaran suhu & regresi Cox pada data historis.")
    w = _peringatan_suhu(lokasi, suhu)
    if w:
        st.warning(w)

    r = tabel[(tabel["produk_id"] == pid) & (tabel["lokasi"] == lokasi)]
    if not r.empty:
        j = r.iloc[0]["jenis"]
        if j in ref.JENIS_NUMERIK:
            st.info(f"Acuan dataset untuk **{lokasi}**: **{r.iloc[0]['rentang_teks']}** sejak diterima.")
        else:
            st.warning(ref.CATATAN_JENIS.get(j, "Tidak ada acuan.") + " Centang tanggal kedaluwarsa kemasan di bawah agar status dapat dihitung.")

    tgl = st.date_input("Tanggal diterima", value=pd.Timestamp(row["tanggal_diterima"]).date() if row else date.today(),
                        max_value=date.today(), key=k("tgl"))
    ada = st.checkbox("Ada tanggal kedaluwarsa pada kemasan", value=bool(row and pd.notna(row["tanggal_kedaluwarsa_aktual"])), key=k("ada"))
    kedaluwarsa = None
    if ada:
        awal = pd.Timestamp(row["tanggal_kedaluwarsa_aktual"]).date() if row and pd.notna(row["tanggal_kedaluwarsa_aktual"]) else date.today() + timedelta(days=7)
        kedaluwarsa = st.date_input("Tanggal kedaluwarsa (aktual, dari kemasan)", value=awal, key=k("exp"))
    catatan = st.text_input("Catatan (opsional)", value=(row["catatan"] or "") if row else "", key=k("cat"))

    b1, b2 = st.columns(2)
    if b1.button("Simpan", type="primary", key=k("simpan")):
        if jumlah <= 0:
            st.error("Jumlah harus lebih dari 0.")
            return
        if kedaluwarsa and kedaluwarsa < tgl:
            st.error("Tanggal kedaluwarsa tidak boleh lebih awal dari tanggal diterima.")
            return
        nama_final = nama.strip() or label[pid].split(" (")[0]
        item_val = None if item_pil == TANPA_ITEM else item_pil
        if row:
            db.ubah_bahan(int(row["id"]), nama_final, int(pid), jumlah, satuan, lokasi, suhu, tgl, kedaluwarsa, catatan.strip(), item=item_val)
        else:
            db.tambah_bahan(nama_final, int(pid), jumlah, satuan, lokasi, suhu, tgl, kedaluwarsa, catatan.strip(), item=item_val)
        st.session_state["notif"] = "Data batch berhasil disimpan."
        st.rerun()
    if b2.button("Batal", key=k("batal")):
        st.rerun()


@st.dialog("Tambah batch bahan")
def dialog_tambah() -> None:
    _form("Tambah", None)


@st.dialog("Ubah batch bahan")
def dialog_ubah(row: dict) -> None:
    _form("Ubah", row)


@st.dialog("Hapus batch bahan")
def dialog_hapus(id_: int, nama: str) -> None:
    st.write(f"Hapus **{nama}** dari inventaris? Tindakan ini tidak dapat dibatalkan.")
    a, b = st.columns(2)
    if a.button("Ya, hapus", type="primary", key="hapus_ya"):
        db.hapus_bahan(id_)
        st.session_state["notif"] = "Batch berhasil dihapus."
        st.rerun()
    if b.button("Batal", key="hapus_batal"):
        st.rerun()


def _muat_contoh() -> int:
    """Muat batch contoh mencakup 4 item restoran (ayam, lamm, steak, koefte) serta bahan pendukung lainnya."""
    contoh_tetap = [
        ("Ayam (Batch Lama)", 118, "ayam", "Kulkas", 1, 3.5, "kg"),
        ("Ayam (Batch Baru)", 118, "ayam", "Kulkas", 0, 5.0, "kg"),
        ("Domba / Lamb", 51, "lamm", "Kulkas", 2, 4.5, "kg"),
        ("Daging Sapi / Steak", 40, "steak", "Kulkas", 1, 6.0, "kg"),
        ("Daging Giling / Koefte", 43, "koefte", "Kulkas", 1, 3.0, "kg"),
    ]
    n = 0
    for nama, pid, item_k, lok, hari, jml, sat in contoh_tetap:
        db.tambah_bahan(nama, pid, jml, sat, lok, 4.0, date.today() - timedelta(days=hari), None, "Contoh data", item=item_k)
        n += 1

    produk, _, tabel = cache.get_reference()
    tambahan = [("Yogurt", "Yogurt", "Kulkas", 9, 1.0, "kg"), ("Eggs (in shell)", "Telur", "Kulkas", 10, 2.0, "kg"),
                ("Tofu", "Tahu", "Kulkas", 5, 1.5, "kg"), ("Shrimp, crayfish", "Udang", "Kulkas", 0, 1.0, "kg")]
    for token, nama, lok, hari, jml, sat in tambahan:
        cand = produk[produk["label"].str.contains(token, case=False, regex=False)]["produk_id"]
        ok = tabel[(tabel["produk_id"].isin(cand)) & (tabel["lokasi"] == lok) & (tabel["jenis"].isin(ref.JENIS_NUMERIK))]
        if not ok.empty:
            db.tambah_bahan(nama, int(ok.iloc[0]["produk_id"]), jml, sat, lok, 4.0,
                            date.today() - timedelta(days=hari), None, "Contoh data")
            n += 1
    return n


def render() -> None:
    ui.page_header(
        "Inventaris Bahan (FEFO)",
        "Kelola batch bahan baku, terima pesanan pemasok, dan urutkan pemakaian dengan aturan FEFO (First-Expired, First-Out).",
    )
    if "notif" in st.session_state:
        st.success(st.session_state.pop("notif"))

    # Panel Terima Pesanan dalam perjalanan
    pes_aktif = db.daftar_pesanan(status="dipesan")
    if not pes_aktif.empty:
        with st.expander(f"Pesanan Pembelian Siap Diterima ({len(pes_aktif)} pesanan dalam perjalanan)", expanded=True):
            ui.tampil_df(pes_aktif.rename(columns={
                "id": "No. Pesanan", "tanggal_pesan": "Tgl Pesan", "nama_pemasok": "Pemasok",
                "item": "Item", "jumlah_kg": "Jumlah (kg)", "status": "Status",
            }), hide_index=True)
            tp1, tp2, tp3 = st.columns([2, 1.2, 1.5])
            id_terima = tp1.selectbox(
                "Pilih pesanan yang tiba", pes_aktif["id"].tolist(),
                format_func=lambda i: f"Pesanan #{i} — {pes_aktif[pes_aktif['id'] == i]['item'].iloc[0]} ({pes_aktif[pes_aktif['id'] == i]['jumlah_kg'].iloc[0]} kg)",
            )
            lok_terima = tp2.selectbox("Simpan ke lokasi", list(cfg.LOKASI), index=1, key="lok_terima")
            if tp3.button("Terima pesanan (masuk stok)", type="primary", icon=":material/download_done:"):
                suhu_def = {"Suhu Ruang": 27.0, "Kulkas": 4.0, "Freezer": -18.0}[lok_terima]
                db.terima_pesanan(int(id_terima), lokasi=lok_terima, suhu_c=suhu_def)
                st.session_state["notif"] = f"Pesanan #{id_terima} diterima dan masuk sebagai batch baru di {lok_terima}."
                st.rerun()

    ev = cache.get_evaluasi()
    tb1, tb2, _ = st.columns([1.4, 1.6, 4])
    if tb1.button("Tambah bahan", type="primary", icon=":material/add:"):
        dialog_tambah()
    if tb2.button("Muat bahan contoh", icon=":material/science:", help="Tambahkan batch contoh ayam, daging, dan bahan lain."):
        st.session_state["notif"] = f"{_muat_contoh()} batch contoh ditambahkan."
        st.rerun()

    if ev.empty:
        ui.empty_state("Inventaris masih kosong", "Klik 'Tambah bahan' atau 'Muat bahan contoh' di atas untuk mulai.")
        ui.kotak_asumsi(tampilkan_mendeley=False)
        return

    f1, f2, f3, f4 = st.columns([2, 1.3, 1.3, 1.3])
    cari = f1.text_input("Cari bahan", placeholder="Ketik nama, item, atau kategori…")
    fk = f2.multiselect("Kategori", sorted(ev["kategori"].unique()))
    fl = f3.multiselect("Lokasi", list(cfg.LOKASI))
    fs = f4.multiselect("Status", list(cfg.STATUS_URUT))
    v = ev
    if cari:
        m = (v["nama"].str.contains(cari, case=False, regex=False)
             | v["kategori"].str.contains(cari, case=False, regex=False)
             | v["item"].fillna("").str.contains(cari, case=False, regex=False))
        v = v[m]
    if fk:
        v = v[v["kategori"].isin(fk)]
    if fl:
        v = v[v["lokasi"].isin(fl)]
    if fs:
        v = v[v["status"].isin(fs)]
    # Urutkan sesuai prioritas FEFO
    v = v.sort_values("urutan_prioritas").reset_index(drop=True)

    t = tables.tabel_tampil(v)
    st.caption(f"Menampilkan {len(v)} dari {len(ev)} batch (diurutkan berdasarkan prioritas **FEFO** — sisa hari terkecil lebih dulu). Klik satu baris untuk aksi.")
    if t.empty:
        ui.empty_state("Tidak ada bahan yang cocok", "Ubah kata kunci atau filter pencarian.")
        pilih = []
    else:
        kolom = [c for c in t.columns if c != "id"]
        cc = {"Suhu (°C)": st.column_config.NumberColumn(format="%.1f"),
              "Umur (hari)": st.column_config.NumberColumn(format="%d"),
              "Sisa (hari)": st.column_config.NumberColumn(format="%d", help="Sisa hari terhadap batas paling awal (estimasi atau aktual)."),
              "FEFO": st.column_config.NumberColumn(format="#%d", help="Urutan konsumsi First-Expired, First-Out untuk produk & lokasi yang sama."),
              "Est. Terbuang (kg)": st.column_config.NumberColumn(format="%.2f", help="Perkiraan kg melewati batas masa simpan pada simulasi konsumsi FEFO.")}
        event = ui.tampil_df(ui.warnai_status(t), hide_index=True, on_select="rerun", selection_mode="single-row",
                             key="tabel_inv", column_order=kolom, column_config=cc)
        pilih = event.selection.rows if event is not None else []

    a, b, c_habis, d_busuk, _ = st.columns([1, 1, 1.8, 1.8, 1.5])
    if a.button("Ubah", disabled=not pilih, icon=":material/edit:"):
        r = v.iloc[pilih[0]]
        dialog_ubah({k: (None if pd.isna(r[k]) else r[k]) for k in ["id", "nama", "produk_id", "item", "jumlah", "satuan", "lokasi", "suhu_c",
                                                                    "tanggal_diterima", "tanggal_kedaluwarsa_aktual", "catatan"]})
    if b.button("Hapus", disabled=not pilih, icon=":material/delete:"):
        r = v.iloc[pilih[0]]
        dialog_hapus(int(r["id"]), r["nama"])
    if c_habis.button("Habis Dipakai (Tersensor)", disabled=not pilih, icon=":material/check_circle:",
                      help="Keluarkan dari stok dan catat ke Data Historis sebagai observasi tersensor (kejadian = 0)."):
        r = v.iloc[pilih[0]]
        db.catat_ke_historis(r["nama"], r["kategori"], r["lokasi"], r["suhu_c"], float(r["umur_hari"]), 0)
        db.hapus_bahan(int(r["id"]))
        st.session_state["notif"] = f"'{r['nama']}' dicatat selesai dipakai (tersensor, kejadian=0) ke Data Historis."
        st.rerun()
    if d_busuk.button("Catat Busuk (Kejadian)", disabled=not pilih, icon=":material/warning:",
                      help="Keluarkan dari stok dan catat ke Data Historis sebagai kejadian pembusukan (kejadian = 1)."):
        r = v.iloc[pilih[0]]
        db.catat_ke_historis(r["nama"], r["kategori"], r["lokasi"], r["suhu_c"], float(r["umur_hari"]), 1)
        db.hapus_bahan(int(r["id"]))
        st.session_state["notif"] = f"'{r['nama']}' dicatat rusak/busuk (kejadian=1) ke Data Historis."
        st.rerun()

    st.markdown("---")
    ui.callout(
        "<b>Aturan FEFO (First-Expired, First-Out):</b> Batch dengan <i>Sisa (hari)</i> paling pendek digunakan lebih dulu "
        "(diikuti tanggal diterima paling awal). Kolom <i>Est. Terbuang (kg)</i> mengestimasi risiko barang melewati batas masa simpan "
        "berdasarkan laju permintaan harian dan probabilitas model Seragam."
    )
    with st.expander("Opsi lanjutan"):
        if st.button("Hapus semua bahan"):
            db.hapus_semua_bahan()
            st.session_state["notif"] = "Seluruh bahan dihapus."
            st.rerun()
    ui.kotak_asumsi(tampilkan_mendeley=False)
