"""Halaman Dataset: Tab Permintaan Harian (Mendeley), Pemetaan Item->FoodKeeper, Parameter Bahan (Mode Data/Manual & Gram/Porsi), Referensi FoodKeeper, dan Data Historis Pembusukan."""
from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

import config as cfg
from core import cache
from core import historical as hist
from core import permintaan as perm_mod
from core import reference as ref
from database import db
from ui import components as ui

TIDAK_ADA = "(tidak ada)"


def _tab_permintaan() -> None:
    st.markdown(
        "**Dataset Permintaan Harian** menjadi dasar perhitungan rata-rata per hari-dalam-minggu, simpangan baku, "
        "indeks musiman bulanan, peramalan, serta simulasi pada bahan bermode **Data**."
    )
    ui.callout(f"<b>Sitasi Wajib (CC BY 4.0):</b> {cfg.SITASI_MENDELEY}", "info")

    df_p = db.muat_permintaan_db()
    if not df_p.empty:
        lap = perm_mod.laporan_kualitas(df_p, satuan="porsi")
        st.caption(f"Data aktif: **{lap['jumlah_hari']} hari** ({lap['tanggal_awal']} s.d. {lap['tanggal_akhir']}) · "
                   f"{lap['jumlah_celah']} celah tanggal · {lap['nilai_kosong']} nilai kosong.")
        ui.tampil_df(df_p.head(15), hide_index=True)

    st.markdown("##### 1. Unggah / Ganti Dataset Permintaan Harian Utama")
    c_u1, c_u2 = st.columns([2, 1])
    f_p = c_u1.file_uploader("Unggah CSV permintaan harian (pemisah ';' atau ',', mendukung format tanggal YYYY-MM-DD maupun M.D.YYYY)",
                             type=["csv", "txt"], key="up_perm_utama")
    if f_p is not None:
        try:
            df_baru = perm_mod.muat_permintaan(f_p)
            st.success(f"File valid: {len(df_baru)} hari ({df_baru['tanggal'].min().strftime('%Y-%m-%d')} s.d. {df_baru['tanggal'].max().strftime('%Y-%m-%d')}).")
            if st.button("Simpan sebagai dataset permintaan aktif", type="primary", icon=":material/save:"):
                db.simpan_permintaan_df(df_baru, sumber="impor", ganti_semua=True)
                st.session_state["notif_ds"] = "Dataset permintaan harian berhasil diperbarui."
                st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Gagal membaca file permintaan: {e}")

    if c_u2.button("Muat ulang dataset bawaan Mendeley (760 hari)", icon=":material/restore:"):
        df_bawaan = perm_mod.muat_permintaan(cfg.BUNDLED_PERMINTAAN)
        db.simpan_permintaan_df(df_bawaan, sumber="impor", ganti_semua=True)
        st.session_state["notif_ds"] = "Dataset bawaan Mendeley (760 hari) berhasil dimuat ulang."
        st.rerun()

    st.divider()
    st.markdown("##### 2. Unggah Data Permintaan untuk Bahan Tertentu (Otomatis Pindah Mode Manual → Data)")
    st.caption("Jika bahan yang semula bermode Manual memiliki riwayat permintaan harian (kolom `tanggal` dan `jumlah_porsi`), "
               "unggah di sini agar modenya otomatis berpindah menjadi **Berbasis data**.")
    u1, u2, u3 = st.columns([1.2, 1, 2])
    kode_it = u1.text_input("Kode bahan (item)", value="udang", key="up_item_kode")
    gram_it = u2.number_input("Asumsi gram per porsi", min_value=10.0, max_value=2000.0, value=200.0, step=10.0, key="up_item_gram")
    f_it = u3.file_uploader("CSV riwayat bahan (kolom: tanggal, jumlah_porsi)", type=["csv"], key="up_item_csv")
    if f_it is not None:
        try:
            raw_it = pd.read_csv(f_it, sep=None, engine="python")
            if "tanggal" not in raw_it.columns or "jumlah_porsi" not in raw_it.columns:
                st.error("CSV harus memiliki kolom 'tanggal' dan 'jumlah_porsi'.")
            else:
                raw_it["tanggal"] = perm_mod.parse_tanggal_fleksibel(raw_it["tanggal"])
                if st.button(f"Impor data '{kode_it}' & ubah ke Mode Data", type="primary"):
                    n_in = db.unggah_permintaan_item(kode_it, raw_it, gram_per_porsi=gram_it)
                    st.session_state["notif_ds"] = f"{n_in} baris permintaan '{kode_it}' disimpan. Mode bahan kini berpindah ke 'Berbasis data'."
                    st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Gagal membaca CSV bahan: {e}")


def _tab_pemetaan_dan_parameter() -> None:
    produk, _, tabel_ref = cache.get_reference()
    label_prod = dict(zip(produk["produk_id"], produk["label"]))
    ids_prod = produk["produk_id"].tolist()

    st.markdown("##### Pemetaan Item Permintaan → Produk USDA FoodKeeper & Asumsi Gram per Porsi")
    st.caption("Ubah pemetaan produk FoodKeeper, asumsi konversi gram per porsi, tingkat layanan, atau tambahkan bahan baru dengan Mode Manual.")

    param_df = db.daftar_parameter_item()
    tampil_p = param_df.copy()
    tampil_p["Produk FoodKeeper"] = tampil_p["produk_id"].map(lambda i: label_prod.get(int(i), "—") if pd.notna(i) else "—")
    ui.tampil_df(tampil_p[[
        "item", "Produk FoodKeeper", "mode_permintaan", "gram_per_porsi", "tingkat_layanan",
        "mean_manual_kg_hari", "cv_manual", "biaya_kurang_per_kg", "biaya_lebih_per_kg",
    ]].rename(columns={
        "item": "Kode Item", "mode_permintaan": "Mode", "gram_per_porsi": "Gram/Porsi (Asumsi)",
        "tingkat_layanan": "Target Layanan", "mean_manual_kg_hari": "Mean Manual (kg/hr)",
        "cv_manual": "CV Manual", "biaya_kurang_per_kg": "Cu (Rp/kg)", "biaya_lebih_per_kg": "Co (Rp/kg)",
    }), hide_index=True)

    st.markdown("##### Ubah / Tambah Parameter Bahan")
    c1, c2, c3 = st.columns([1.2, 2.2, 1])
    item_edit = c1.text_input("Kode bahan (item)", value="ayam", help="Gunakan ayam/lamm/steak/koefte atau ketik nama bahan baru.")
    ada_cfg = db.get_parameter_item(item_edit)
    pid_def = int(ada_cfg["produk_id"]) if (ada_cfg and pd.notna(ada_cfg.get("produk_id")) and int(ada_cfg["produk_id"]) in ids_prod) else 118
    pid_pil = c2.selectbox("Produk acuan FoodKeeper", ids_prod, index=ids_prod.index(pid_def),
                           format_func=lambda i: f"ID {i} — {label_prod[i]}")
    mode_pil = c3.selectbox("Mode permintaan", ["data", "manual"],
                            index=0 if (ada_cfg and ada_cfg.get("mode_permintaan") == "data") else 1)

    c4, c5, c6, c7 = st.columns(4)
    gram_pil = c4.number_input("Gram per porsi (asumsi)", min_value=10.0, max_value=2000.0,
                               value=float((ada_cfg or {}).get("gram_per_porsi") or cfg.GRAM_PER_PORSI.get(item_edit, 200.0)), step=10.0)
    sl_pil = c5.number_input("Target layanan (0,80–0,99)", min_value=0.80, max_value=0.99,
                             value=float((ada_cfg or {}).get("tingkat_layanan") or 0.95), step=0.01)
    mean_pil = c6.number_input("Mean manual (kg/hari)", min_value=0.0,
                               value=float((ada_cfg or {}).get("mean_manual_kg_hari") or 4.0), step=0.5)
    cv_pil = c7.number_input("CV manual (0,10–0,60)", min_value=0.10, max_value=0.60,
                             value=float((ada_cfg or {}).get("cv_manual") or 0.30), step=0.01)

    c8, c9, c10 = st.columns(3)
    cu_pil = c8.number_input("Biaya kurang stok Cu (Rp/kg)", min_value=0.0,
                             value=float((ada_cfg or {}).get("biaya_kurang_per_kg") or 60000.0), step=5000.0)
    co_pil = c9.number_input("Biaya barang busuk Co (Rp/kg)", min_value=0.0,
                             value=float((ada_cfg or {}).get("biaya_lebih_per_kg") or 40000.0), step=5000.0)
    prof_pil = c10.checkbox("Pinjam profil hari dari data daging (mode manual)",
                            value=bool((ada_cfg or {}).get("pakai_profil_hari", 0)))

    if st.button("Simpan parameter & pemetaan bahan", type="primary", icon=":material/save:"):
        db.simpan_parameter_item(
            item_edit, pid_pil, gram_per_porsi=gram_pil, tingkat_layanan=sl_pil,
            biaya_kurang_per_kg=cu_pil, biaya_lebih_per_kg=co_pil,
            mode_permintaan=mode_pil, mean_manual_kg_hari=mean_pil,
            cv_manual=cv_pil, pakai_profil_hari=int(prof_pil),
        )
        st.session_state["notif_ds"] = f"Parameter dan pemetaan untuk '{item_edit}' berhasil disimpan."
        st.rerun()


def _tab_referensi() -> None:
    produk, kategori, tabel = cache.get_reference()
    sumber = "unggahan Anda" if ref.using_user_reference() else "dataset bawaan (FoodKeeper-Data.xls)"
    ui.callout(f"<b>Referensi aktif:</b> {sumber} · {len(produk)} produk · {kategori['kategori_id'].nunique()} kategori. "
               "Referensi memuat <i>rentang masa simpan</i> per produk dan lokasi, bukan pengamatan pembusukan.", "info")

    st.markdown("##### Pemetaan Standar Item Restoran di FoodKeeper")
    peta_std = []
    for it, pid in db.peta_item_ke_produk_id().items():
        pr = produk[produk["produk_id"] == pid]
        nm = pr["label"].iloc[0] if not pr.empty else "—"
        tk = tabel[(tabel["produk_id"] == pid) & (tabel["lokasi"] == "Kulkas")]
        tf = tabel[(tabel["produk_id"] == pid) & (tabel["lokasi"] == "Freezer")]
        peta_std.append({
            "Item": cfg.ITEM_LABEL.get(it, it),
            "Produk ID": pid,
            "Nama Produk FoodKeeper": nm,
            "Masa Simpan Kulkas": tk["rentang_teks"].iloc[0] if not tk.empty else "—",
            "Masa Simpan Freezer": tf["rentang_teks"].iloc[0] if not tf.empty else "—",
        })
    ui.tampil_df(pd.DataFrame(peta_std), hide_index=True)

    st.markdown("##### Cakupan data masa simpan")
    cov = tabel.pivot_table(index="lokasi", columns="jenis", values="produk_id", aggfunc="count", fill_value=0)
    cov["Total produk"] = len(produk)
    cov["Memiliki angka (hari)"] = cov[[c for c in ref.JENIS_NUMERIK if c in cov]].sum(axis=1)
    cov["Cakupan (%)"] = (cov["Memiliki angka (hari)"] / len(produk) * 100).round(1)
    cov = cov[["Total produk", "Memiliki angka (hari)", "Cakupan (%)"] + [c for c in cov.columns if c not in ("Total produk", "Memiliki angka (hari)", "Cakupan (%)")]]
    ui.tampil_df(cov.reset_index().rename(columns={"lokasi": "Lokasi"}), hide_index=True)

    st.markdown("##### Ganti dataset referensi")
    f = st.file_uploader("Unggah file berformat FoodKeeper (sheet 'Product' dan 'Category')", type=["xls", "xlsx"], key="up_ref")
    if f is not None:
        try:
            engine = "xlrd" if f.name.lower().endswith(".xls") else "openpyxl"
            p = pd.read_excel(f, sheet_name="Product", engine=engine)
            c = pd.read_excel(f, sheet_name="Category", engine=engine)
        except Exception as e:  # noqa: BLE001
            st.error(f"Sheet 'Product' dan 'Category' tidak dapat dibaca: {e}")
            return
        masalah = ref.validate_reference(p, c)
        if masalah:
            for m in masalah:
                st.error(m)
        else:
            st.success(f"Format valid: {len(p)} produk, {len(c)} kategori.")
            if st.button("Gunakan sebagai referensi", type="primary"):
                p.to_csv(cfg.USER_PRODUCT, index=False)
                c.to_csv(cfg.USER_CATEGORY, index=False)
                cache.hapus_cache_referensi()
                st.session_state["notif_ds"] = "Referensi diganti."
                st.rerun()
    if ref.using_user_reference() and st.button("Kembalikan ke dataset bawaan"):
        cfg.USER_PRODUCT.unlink(missing_ok=True)
        cfg.USER_CATEGORY.unlink(missing_ok=True)
        cache.hapus_cache_referensi()
        st.session_state["notif_ds"] = "Dataset bawaan dipulihkan."
        st.rerun()


def _tab_historis() -> None:
    st.markdown(
        "**Data historis pembusukan (opsional)** adalah catatan observasi masa lalu (berapa hari bahan bertahan dan apakah akhirnya rusak). "
        "Data ini hanya diperlukan jika Anda ingin mengaktifkan analisis survival lanjutan (Kaplan-Meier dan Cox PH)."
    )
    meta = db.meta_historis()
    if meta:
        ui.callout(f"<b>Data historis aktif:</b> {meta['nama_file']} · {meta['baris_valid']} observasi valid "
                   f"({meta['kejadian']} kejadian pembusukan, {meta['baris_valid'] - meta['kejadian']} tersensor) · "
                   f"diperbarui {meta['diunggah'].replace('T', ' ')}", "ok")
        with st.expander("Lihat isi data historis aktif"):
            ui.tampil_df(db.muat_historis(), hide_index=True)
        if st.button("Hapus data historis aktif", icon=":material/delete:"):
            db.hapus_historis()
            st.session_state["notif_ds"] = "Data historis dihapus."
            st.rerun()

    b_c1, b_c2 = st.columns(2)
    if b_c1.button("Muat data historis contoh (72 observasi)", icon=":material/science:"):
        df_c = hist.buat_contoh_historis()
        db.simpan_historis(df_c, "contoh_observasi_historis.csv", len(df_c), "{}")
        st.session_state["notif_ds"] = "72 observasi contoh dimuat."
        st.rerun()
    b_c2.download_button("Unduh template CSV contoh", hist.template_historis_csv(), "template_data_historis.csv",
                         "text/csv", icon=":material/download:")

    f = st.file_uploader("Unggah CSV atau Excel observasi pembusukan (.csv, .xlsx, .xls)", type=["csv", "xlsx", "xls", "tsv", "txt"], key="up_hist")
    if f is None:
        return
    try:
        df = hist.baca_unggahan(f.name, f.getvalue())
    except ValueError as e:
        st.error(str(e))
        return
    if df.empty:
        st.error("File tidak berisi data.")
        return

    ui.tampil_df(df.head(15), hide_index=True)
    tebak = hist.tebak_pemetaan(df)
    kolom_opsi = [TIDAK_ADA] + list(df.columns)
    peta = {}
    cols = st.columns(2)
    for i, kunci in enumerate(["durasi", "kejadian", "lokasi", "suhu", "kategori", "nama", "mulai", "akhir"]):
        awal = tebak.get(kunci)
        peta[kunci] = cols[i % 2].selectbox(hist.LABEL_KOLOM[kunci], kolom_opsi,
                                           index=kolom_opsi.index(awal) if awal in kolom_opsi else 0, key=f"peta_{f.name}_{kunci}")
        peta[kunci] = None if peta[kunci] == TIDAK_ADA else peta[kunci]

    bersih, lap = hist.praproses(df, peta)
    for g in lap["galat"]:
        st.error(g)
    if not bersih.empty:
        if st.button("Simpan sebagai data historis aktif", type="primary", icon=":material/save:"):
            db.simpan_historis(bersih, f.name, lap["baris_awal"], json.dumps(lap, default=str))
            st.session_state["notif_ds"] = "Data historis pembusukan disimpan."
            st.rerun()


def render() -> None:
    ui.page_header(
        "Dataset & Konfigurasi Parameter",
        "Kelola dataset permintaan harian (Mendeley), pemetaan item ke USDA FoodKeeper, parameter bahan (Mode Data/Manual), dan data historis.",
    )
    if "notif_ds" in st.session_state:
        st.success(st.session_state.pop("notif_ds"))

    t1, t2, t3, t4 = st.tabs([
        "1. Permintaan Harian (Mendeley)",
        "2. Parameter Bahan & Pemetaan Item",
        "3. Referensi USDA FoodKeeper",
        "4. Data Historis Pembusukan (Opsional)",
    ])
    with t1:
        _tab_permintaan()
    with t2:
        _tab_pemetaan_dan_parameter()
    with t3:
        _tab_referensi()
    with t4:
        _tab_historis()

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=True, mode_manual=True)
