"""Halaman Laporan: Ekspor CSV Rencana Pengadaan, CSV Inventaris FEFO, dan PDF Ringkasan Lengkap (Parameter, Asumsi, Simulasi, Sitasi)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import config as cfg
from core import cache, reports, stats
from core import procurement as proc
from core import shelf_life as sl
from core import simulasi as sim_mod
from database import db
from ui import components as ui
from ui import tables


def _susun_tabel_rencana_semua(df_kg: pd.DataFrame, tabel_ref: pd.DataFrame) -> pd.DataFrame:
    param_db = db.daftar_parameter_item()
    peta_pid = db.peta_item_ke_produk_id()
    semua = []
    for _, r in param_db.iterrows():
        item = str(r["item"])
        pid = int(r["produk_id"]) if pd.notna(r["produk_id"]) else peta_pid.get(item, 118)
        info_sup = db.info_pemasok_untuk_item(item)
        ms_info = sl.masa_simpan_produk(tabel_ref, pid, "Kulkas")
        ms_hari = float(ms_info["min_hari"]) if pd.notna(ms_info["min_hari"]) and ms_info["min_hari"] > 0 else 2.0
        kol_kg = f"{item}_kg"
        if r["mode_permintaan"] == "data" and not df_kg.empty and kol_kg in df_kg.columns:
            p_hari = proc.parameter_per_hari(df_kg, kol_kg)
            res = proc.rasio_residual_harian(df_kg, kol_kg)
        else:
            p_hari = proc.parameter_manual(float(r["mean_manual_kg_hari"] or 4.0), cv=float(r["cv_manual"] or 0.30))
            res = None
        stok_kg, pipe_kg = db.stok_dan_pipeline_kg(item, lokasi="Kulkas")
        tbl_m, _ = proc.tabel_perencanaan_mingguan(
            p_hari, L_hari=float(info_sup["lead_time_rata"]), R_hari=1.0,
            tingkat_layanan=float(r["tingkat_layanan"] or 0.95), masa_simpan_hari=ms_hari,
            std_L=float(info_sup["lead_time_std"]), residual_rasio=res,
            stok_sekarang=stok_kg, pipeline_kg=pipe_kg, moq_kg=float(info_sup["moq_kg"]),
        )
        tbl_m.insert(0, "Item", cfg.ITEM_LABEL.get(item, item.title()))
        semua.append(tbl_m.drop(columns=["hari"]))
    return pd.concat(semua, ignore_index=True) if semua else pd.DataFrame()


def render() -> None:
    ui.page_header(
        "Laporan & Ekspor",
        "Ringkasan rencana pengadaan mingguan, hasil simulasi kebijakan, prioritas konsumsi FEFO, dan unduhan CSV/PDF.",
    )
    ev = cache.get_evaluasi()
    produk, _, tabel_ref = cache.get_reference()
    df_kg = cache.get_permintaan_kg()
    desk = stats.deskriptif_per_lokasi(stats.tabel_numerik(tabel_ref, produk))

    df_rencana = _susun_tabel_rencana_semua(df_kg, tabel_ref)
    if not df_kg.empty and "ayam_kg" in df_kg.columns:
        p_ayam = proc.parameter_per_hari(df_kg, "ayam_kg")
        df_sim = sim_mod.bandingkan_kebijakan(p_ayam, df_kg=df_kg, kolom="ayam_kg", mode="backtest", masa_simpan_hari=1.0)
    else:
        df_sim = pd.DataFrame()

    st.markdown("##### 1. Rencana Pengadaan Mingguan (Semua Bahan Terdaftar)")
    if not df_rencana.empty:
        ui.tampil_df(df_rencana, hide_index=True)

    if not df_sim.empty:
        st.markdown("##### 2. Ringkasan Evaluasi Simulasi Kebijakan (Studi Kasus Ayam — Backtest 760 Hari)")
        kol_s = ["Kebijakan", "% Hari Kehabisan Stok", "Tingkat Layanan (%)", "Fill Rate (%)",
                 "Barang Terbuang (kg)", "Rata-rata Stok (kg)", "Total Biaya Risiko (Rp)", "sumber"]
        ui.tampil_df(df_sim[kol_s], hide_index=True)

    st.markdown("##### 3. Rekomendasi Prioritas Konsumsi Batch (FEFO — First-Expired, First-Out)")
    if ev.empty:
        st.caption("Inventaris batch saat ini masih kosong.")
    else:
        pri = tables.tabel_prioritas(ev).drop(columns=["FIFO"], errors="ignore")
        ui.tampil_df(ui.warnai_status(pri), hide_index=True)

    st.markdown("##### 4. Unduh Laporan")
    tgl = date.today().isoformat()
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button(
        "Unduh CSV Rencana Pengadaan",
        reports.csv_rencana_pengadaan(df_rencana),
        f"rencana_pengadaan_{tgl}.csv",
        "text/csv",
        icon=":material/download:",
    )
    c2.download_button(
        "Unduh CSV Inventaris FEFO",
        reports.csv_inventaris(ev) if not ev.empty else b"Inventaris kosong",
        f"laporan_inventaris_fefo_{tgl}.csv",
        "text/csv",
        icon=":material/download:",
    )
    c3.download_button(
        "Unduh CSV Statistik Masa Simpan",
        reports.csv_statistik(desk),
        f"statistik_masa_simpan_{tgl}.csv",
        "text/csv",
        icon=":material/download:",
    )
    kol_pdf_r = ["Item", "Hari", "Mean (kg)", "Std (kg)", "SS Normal (kg)", "SS Empiris (kg)", "ROP (kg)",
                 "Target Stok S (kg)", "Stok Maks S_cap (kg)", "Jumlah Pesan q (kg)", "sumber"]
    df_r_pdf = df_rencana[kol_pdf_r].head(28) if not df_rencana.empty else None
    df_s_pdf = df_sim[["Kebijakan", "% Hari Kehabisan Stok", "Tingkat Layanan (%)", "Fill Rate (%)",
                       "Barang Terbuang (kg)", "Rata-rata Stok (kg)", "sumber"]] if not df_sim.empty else None
    c4.download_button(
        "Unduh PDF Laporan Lengkap",
        reports.pdf_laporan(ev, desk, db.meta_historis(), df_rencana=df_r_pdf, df_simulasi=df_s_pdf,
                            gram_per_porsi=db.peta_gram_per_porsi()),
        f"laporan_supply_chain_{tgl}.pdf",
        "application/pdf",
        type="primary",
        icon=":material/picture_as_pdf:",
    )

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=True, mode_manual=True)
