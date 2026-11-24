"""Halaman Simulasi & Evaluasi: Backtest & Monte Carlo (Kebijakan A vs B vs C) dan analisis trade-off layanan vs barang terbuang."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from core import cache
from core import procurement as proc
from core import shelf_life as sl
from core import simulasi as sim_mod
from database import db
from ui import components as ui


def render() -> None:
    ui.page_header(
        "Simulasi & Evaluasi Kebijakan",
        "Bandingkan Kebijakan A (Naif), B (ROP + Safety Stock), dan C (ROP + Safety Stock + Batas Masa Simpan) dengan konsumsi FEFO.",
    )
    produk, _, tabel_ref = cache.get_reference()
    df_kg = cache.get_permintaan_kg()
    peta_pid = db.peta_item_ke_produk_id()

    opsi_item = ["ayam", "daging", "lamm", "steak", "koefte", "manual_custom"]
    label_map = {**cfg.ITEM_LABEL, "manual_custom": "Bahan Lain (Simulasi Mode Manual - Asumsi Pengguna)"}

    c1, c2, c3, c4 = st.columns(4)
    item = c1.selectbox("Bahan yang disimulasikan", opsi_item, format_func=lambda k: label_map.get(k, k.title()))
    mode_manual = (item == "manual_custom") or (df_kg.empty) or (f"{item}_kg" not in df_kg.columns)
    mode_sim = c2.selectbox(
        "Metode evaluasi",
        ["backtest", "montecarlo"] if not mode_manual else ["montecarlo"],
        format_func=lambda m: "Backtest Data Nyata (760 hari)" if m == "backtest" else "Monte Carlo Bootstrap / Parametrik (1.000 hari)",
    )
    layanan_pct = c3.slider("Target tingkat layanan (%)", min_value=85, max_value=99, value=95, step=1)
    tingkat_layanan = layanan_pct / 100.0
    L_rata = c4.slider("Lead time rata-rata L (hari)", min_value=1.0, max_value=5.0, value=1.0, step=0.5)

    c5, c6, c7, c8 = st.columns(4)
    pid_sim = peta_pid.get(item, 118)
    ms_info = sl.masa_simpan_produk(tabel_ref, pid_sim, "Kulkas")
    ms_def = float(ms_info["min_hari"]) if pd.notna(ms_info["min_hari"]) and ms_info["min_hari"] > 0 else 2.0
    masa_simpan = c5.number_input("Masa simpan bahan (hari)", min_value=1.0, max_value=30.0, value=ms_def, step=0.5)
    L_std = c6.number_input("Variasi lead time s_L (hari)", min_value=0.0, max_value=2.0, value=0.0, step=0.1)
    cu_val = c7.number_input("Biaya kehabisan stok Cu (Rp/kg)", min_value=1000.0, value=60000.0, step=5000.0)
    co_val = c8.number_input("Biaya barang busuk Co (Rp/kg)", min_value=1000.0, value=40000.0, step=5000.0)

    if mode_manual:
        mm1, mm2 = st.columns(2)
        mean_m = mm1.number_input("Rata-rata permintaan manual (kg/hari)", min_value=0.5, value=5.0, step=0.5)
        cv_m = mm2.slider("Koefisien variasi manual (CV)", min_value=0.10, max_value=0.60, value=0.30, step=0.01)
        param_hari = proc.parameter_manual(mean_m, cv=cv_m)
        kol_kg = None
    else:
        kol_kg = f"{item}_kg"
        param_hari = proc.parameter_per_hari(df_kg, kol_kg)

    sumber_lbl = "asumsi" if mode_manual else "data"
    st.markdown(f"**Status Simulasi:** {ui.lencana_sumber(sumber_lbl)} &nbsp; <span class='badge b-info'>Seed tetap = 42 (Reproducible)</span>",
                unsafe_allow_html=True)

    hasil = sim_mod.bandingkan_kebijakan(
        param_hari, df_kg=df_kg if not mode_manual else None, kolom=kol_kg,
        mode=mode_sim, n_hari_simulasi=1000, masa_simpan_hari=masa_simpan,
        L_rata=L_rata, L_std=L_std, tingkat_layanan=tingkat_layanan,
        Cu=cu_val, Co=co_val, seed=42,
    )

    st.markdown("##### Perbandingan Kinerja 3 Kebijakan Persediaan (FEFO)")
    fmt_s = {
        "% Hari Kehabisan Stok": st.column_config.NumberColumn(format="%.2f%%"),
        "CI 95% Bawah (%)": st.column_config.NumberColumn(format="%.2f%%"),
        "CI 95% Atas (%)": st.column_config.NumberColumn(format="%.2f%%"),
        "Tingkat Layanan (%)": st.column_config.NumberColumn(format="%.2f%%"),
        "Fill Rate (%)": st.column_config.NumberColumn(format="%.2f%%"),
        "Barang Terbuang (kg)": st.column_config.NumberColumn(format="%.2f"),
        "Kekurangan Stok (kg)": st.column_config.NumberColumn(format="%.2f"),
        "Rata-rata Stok (kg)": st.column_config.NumberColumn(format="%.2f"),
        "Total Biaya Risiko (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
    }
    kol_tampil = ["Kebijakan", "n_hari", "% Hari Kehabisan Stok", "CI 95% Bawah (%)", "CI 95% Atas (%)",
                  "Tingkat Layanan (%)", "Fill Rate (%)", "Barang Terbuang (kg)", "Rata-rata Stok (kg)", "Total Biaya Risiko (Rp)", "sumber"]
    ui.tampil_df(hasil[kol_tampil].rename(columns={"n_hari": "Hari Uji", "sumber": "Sumber"}), hide_index=True, column_config=fmt_s)

    terbaik = hasil.sort_values("Total Biaya Risiko (Rp)").iloc[0]
    ui.callout(
        f"<b>Rekomendasi Kebijakan Terbaik:</b> <b>{terbaik['Kebijakan']}</b> menghasilkan total biaya risiko terendah "
        f"(<b>Rp {ui.angka(terbaik['Total Biaya Risiko (Rp)'], 0)}</b>) dengan tingkat layanan "
        f"<b>{ui.angka(terbaik['Tingkat Layanan (%)'], 1)}%</b> (fill rate <b>{ui.angka(terbaik['Fill Rate (%)'], 1)}%</b>) "
        f"dan barang terbuang <b>{ui.angka(terbaik['Barang Terbuang (kg)'], 2)} kg</b>.",
        "ok",
    )

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### Trade-off Tingkat Layanan vs Barang Terbuang")
        fig_tr = go.Figure()
        fig_tr.add_bar(x=hasil["Kebijakan"], y=hasil["Tingkat Layanan (%)"], name="Tingkat Layanan (%)", marker_color="#2563EB")
        fig_tr.add_bar(x=hasil["Kebijakan"], y=hasil["Fill Rate (%)"], name="Fill Rate (%)", marker_color="#0891B2")
        fig_tr.update_layout(barmode="group", yaxis_title="Persentase (%)", yaxis_range=[0, 105])
        ui.tampil_grafik(fig_tr, "sim_layanan")
    with g2:
        st.markdown("##### Barang Terbuang (kg) & Rata-rata Stok (kg)")
        fig_w = go.Figure()
        fig_w.add_bar(x=hasil["Kebijakan"], y=hasil["Barang Terbuang (kg)"], name="Barang Terbuang (kg)", marker_color="#DC2626")
        fig_w.add_bar(x=hasil["Kebijakan"], y=hasil["Rata-rata Stok (kg)"], name="Rata-rata Stok (kg)", marker_color="#D97706")
        fig_w.update_layout(barmode="group", yaxis_title="Kilogram (kg)")
        ui.tampil_grafik(fig_w, "sim_waste")

    st.markdown("##### Kurva Trade-off Kuantitatif Lintas Target Layanan (Kebijakan C)")
    titik_sl = [0.85, 0.90, 0.93, 0.95, 0.97, 0.99]
    kurva_baris = []
    for sl_v in titik_sl:
        df_sl = sim_mod.bandingkan_kebijakan(
            param_hari, df_kg=df_kg if not mode_manual else None, kolom=kol_kg,
            mode=mode_sim, n_hari_simulasi=1000, masa_simpan_hari=masa_simpan,
            L_rata=L_rata, L_std=L_std, tingkat_layanan=sl_v, Cu=cu_val, Co=co_val, seed=42,
        )
        rc = df_sl[df_sl["Kebijakan"] == sim_mod.KEBIJAKAN_C].iloc[0]
        kurva_baris.append({
            "Target Layanan (%)": sl_v * 100.0,
            "Layanan Aktual (%)": rc["Tingkat Layanan (%)"],
            "Barang Terbuang (kg)": rc["Barang Terbuang (kg)"],
            "Total Biaya Risiko (Rp)": rc["Total Biaya Risiko (Rp)"],
        })
    df_kurva = pd.DataFrame(kurva_baris)
    opt_sl = df_kurva.sort_values("Total Biaya Risiko (Rp)").iloc[0]
    st.caption(f"Titik target layanan paling ekonomis pada parameter ini: **{opt_sl['Target Layanan (%)']:.0f}%** "
               f"(layanan aktual {opt_sl['Layanan Aktual (%)']:.1f}%, terbuang {opt_sl['Barang Terbuang (kg)']:.2f} kg).")

    with st.expander("Lihat rumus Simulasi, Fill Rate, dan CI Wilson Proporsi Kehabisan Stok"):
        st.latex(r"\text{Cycle Service Level} = 1 - \frac{\text{Hari Stockout}}{N_{\text{hari}}}, \qquad "
                 r"\text{Fill Rate} = \frac{\sum_{t=1}^{N}\min(D_t, \text{Stok}_{\text{tersedia},t})}{\sum_{t=1}^{N} D_t}")
        st.latex(r"\text{Total Biaya Risiko} = C_u \sum_{t=1}^{N}\max(0, D_t - \text{Stok}_t) + C_o \sum_{t=1}^{N}\text{Terbuang}_t")
        st.caption("Interval kepercayaan 95% untuk persentase hari kehabisan stok dihitung menggunakan metode skor Wilson.")

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=True, mode_manual=mode_manual)
