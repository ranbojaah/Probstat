"""Halaman Dashboard Ketersediaan Bahan Baku (Supply Chain) & Masa Simpan FEFO."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from core import cache
from core import procurement as proc
from core import shelf_life as sl
from database import db
from ui import components as ui
from ui import tables


def _ringkasan_pengadaan_hari_ini(df_kg: pd.DataFrame, tabel_ref: pd.DataFrame) -> pd.DataFrame:
    """Susun status stok vs ROP vs batas masa simpan (S_cap) untuk hari ini pada seluruh item di parameter_item."""
    hari_ini = date.today().weekday()
    param_db = db.daftar_parameter_item()
    peta_pid = db.peta_item_ke_produk_id()
    baris = []

    for _, r in param_db.iterrows():
        item = str(r["item"])
        pid = int(r["produk_id"]) if pd.notna(r["produk_id"]) else peta_pid.get(item)
        info_sup = db.info_pemasok_untuk_item(item)
        L_hari = float(info_sup["lead_time_rata"])
        std_L = float(info_sup["lead_time_std"])
        moq = float(info_sup["moq_kg"])
        layanan = float(r["tingkat_layanan"] or 0.95)

        ms_info = sl.masa_simpan_produk(tabel_ref, pid, "Kulkas")
        ms_hari = float(ms_info["min_hari"]) if pd.notna(ms_info["min_hari"]) and ms_info["min_hari"] > 0 else 2.0

        kol_kg = f"{item}_kg"
        if r["mode_permintaan"] == "data" and not df_kg.empty and kol_kg in df_kg.columns:
            p_hari = proc.parameter_per_hari(df_kg, kol_kg)
        else:
            p_hari = proc.parameter_manual(float(r["mean_manual_kg_hari"] or 4.0), cv=float(r["cv_manual"] or 0.30))

        stok_kg, pipe_kg = db.stok_dan_pipeline_kg(item, lokasi="Kulkas")
        tbl_m, _ = proc.tabel_perencanaan_mingguan(
            p_hari, L_hari=L_hari, R_hari=1.0, tingkat_layanan=layanan,
            masa_simpan_hari=ms_hari, std_L=std_L, stok_sekarang=stok_kg,
            pipeline_kg=pipe_kg, moq_kg=moq,
        )
        bh = tbl_m[tbl_m["hari"] == hari_ini].iloc[0]
        mean_h = float(bh["Mean (kg)"])
        hari_cukup = ((stok_kg + pipe_kg) / mean_h) if mean_h > 0 else 99.0
        baris.append({
            "item": item,
            "Bahan": cfg.ITEM_LABEL.get(item, item.title()),
            "Sumber": str(bh["sumber"]),
            "Hari": cfg.HARI_ID[hari_ini],
            "Mean Hari Ini (kg)": round(mean_h, 2),
            "Stok Sekarang (kg)": round(stok_kg, 2),
            "Pipeline (kg)": round(pipe_kg, 2),
            "ROP (kg)": round(float(bh["ROP (kg)"]), 2),
            "Target Stok S (kg)": round(float(bh["Target Stok S (kg)"]), 2),
            "Batas Masa Simpan S_cap (kg)": round(float(bh["Stok Maks S_cap (kg)"]), 2),
            "Saran Pesan (kg)": round(float(bh["Jumlah Pesan q (kg)"]), 2),
            "Cukup Untuk (hari)": round(hari_cukup, 1),
            "Layanan Target (%)": round(layanan * 100.0, 1),
            "Pemasok": info_sup["nama_pemasok"],
            "pemasok_id": info_sup["pemasok_id"],
            "di_bawah_rop": (stok_kg + pipe_kg) < float(bh["ROP (kg)"]),
            "risiko_habis_3hr": hari_cukup <= 3.0,
        })
    return pd.DataFrame(baris)


def render() -> None:
    ui.page_header(
        "Dashboard Ketersediaan Bahan Baku",
        "Pemantauan ketersediaan stok terhadap Reorder Point (ROP), batas masa simpan, prioritas konsumsi FEFO, dan rekomendasi pemesanan hari ini.",
    )
    if "notif_dash" in st.session_state:
        st.success(st.session_state.pop("notif_dash"))

    produk, _, tabel_ref = cache.get_reference()
    df_kg = cache.get_permintaan_kg()
    ev = cache.get_evaluasi()
    ring_rop = _ringkasan_pengadaan_hari_ini(df_kg, tabel_ref)

    n_bawah_rop = int(ring_rop["di_bawah_rop"].sum()) if not ring_rop.empty else 0
    n_risiko_habis = int(ring_rop["risiko_habis_3hr"].sum()) if not ring_rop.empty else 0
    n_kritis = int((ev["status"] == cfg.KRITIS).sum()) if not ev.empty else 0
    est_waste = float(ev["estimasi_busuk_kg"].sum()) if (not ev.empty and "estimasi_busuk_kg" in ev.columns) else 0.0
    rata_layanan = float(ring_rop["Layanan Target (%)"].mean()) if not ring_rop.empty else 95.0

    ui.kpi_grid([
        dict(label="Bahan di bawah ROP", value=f"{n_bawah_rop} item",
             hint="Perlu dipesan ulang hari ini", tone="kritis" if n_bawah_rop > 0 else "aman"),
        dict(label="Berisiko habis (1–3 hari)", value=f"{n_risiko_habis} item",
             hint="Stok + pipeline ≤ kebutuhan 3 hari", tone="segera" if n_risiko_habis > 0 else "aman"),
        dict(label="Batch Kritis (masa simpan)", value=f"{n_kritis} batch",
             hint="Sudah mencapai/melewati estimasi masa simpan", tone="kritis" if n_kritis > 0 else "aman"),
        dict(label="Perkiraan barang terbuang", value=f"{ui.angka(est_waste, 2)} kg",
             hint="Simulasi konsumsi FEFO terhadap laju permintaan", tone="segera" if est_waste > 0 else "aman"),
        dict(label="Target tingkat layanan", value=f"{ui.angka(rata_layanan, 1)}%",
             hint="Target Cycle Service Level ≥ 95%", tone="info"),
    ])

    st.markdown(f"##### Tabel Perlu Dipesan Hari Ini ({cfg.HARI_ID[date.today().weekday()]})")
    if ring_rop.empty:
        ui.empty_state("Belum ada parameter bahan", "Atur parameter bahan di halaman Perencanaan Pengadaan atau Dataset.")
    else:
        kol_t = ["Bahan", "Sumber", "Stok Sekarang (kg)", "Pipeline (kg)", "ROP (kg)",
                 "Batas Masa Simpan S_cap (kg)", "Saran Pesan (kg)", "Cukup Untuk (hari)", "Pemasok"]
        ui.tampil_df(ring_rop[kol_t], hide_index=True)
        perlu = ring_rop[ring_rop["Saran Pesan (kg)"] > 0]
        if not perlu.empty:
            if st.button("Buat pesanan otomatis untuk semua item yang perlu dipesan hari ini", type="primary", icon=":material/shopping_cart:"):
                n_ord = 0
                for _, rp in perlu.iterrows():
                    db.buat_pesanan(rp["item"], float(rp["Saran Pesan (kg)"]), pemasok_id=rp["pemasok_id"])
                    n_ord += 1
                st.session_state["notif_dash"] = f"{n_ord} pesanan pembelian berhasil dibuat. Terima barang di halaman Inventaris Bahan."
                st.rerun()

    kiri, kanan = st.columns(2)
    with kiri:
        st.markdown("##### Stok Sekarang vs ROP vs Batas Masa Simpan ($S_{cap}$)")
        if not ring_rop.empty:
            fig_rop = go.Figure()
            fig_rop.add_bar(x=ring_rop["Bahan"], y=ring_rop["Stok Sekarang (kg)"], name="Stok Sekarang (kg)", marker_color="#16A34A")
            fig_rop.add_bar(x=ring_rop["Bahan"], y=ring_rop["ROP (kg)"], name="Reorder Point (ROP)", marker_color="#2563EB")
            fig_rop.add_bar(x=ring_rop["Bahan"], y=ring_rop["Batas Masa Simpan S_cap (kg)"], name="Batas Masa Simpan (S_cap)", marker_color="#DC2626")
            fig_rop.update_layout(barmode="group", yaxis_title="Kilogram (kg)")
            ui.tampil_grafik(fig_rop, "dash_stok_rop")
    with kanan:
        st.markdown("##### Prioritas Konsumsi Lebih Dulu (FEFO — First-Expired, First-Out)")
        if ev.empty:
            ui.empty_state("Belum ada batch di inventaris",
                           "Tambahkan batch atau klik 'Muat bahan contoh' di halaman Inventaris Bahan.")
            ui.link_halaman("inventaris", "Buka Inventaris Bahan", ":material/inventory_2:")
        else:
            top = ev.sort_values("urutan_prioritas").head(5)
            baris = ""
            for _, r in top.iterrows():
                sisa = "—" if pd.isna(r["sisa_efektif"]) else f"sisa {int(r['sisa_efektif'])} hari"
                w_kg = f" · est. busuk {ui.angka(r['estimasi_busuk_kg'], 2)} kg" if r.get("estimasi_busuk_kg", 0) > 0 else ""
                baris += (f"<div class='prio'><div class='n'>{int(r['urutan_prioritas'])}</div><div>"
                          f"<div class='t'>{r['nama']} {ui.badge(r['status'])}</div>"
                          f"<div class='s'>{r['lokasi']} · FEFO #{int(r['urutan_fefo'])} · diterima {ui.tanggal(r['tanggal_diterima'])} · {sisa}{w_kg}</div></div></div>")
            st.markdown(f"<div class='card'>{baris}</div>", unsafe_allow_html=True)

    if not ev.empty:
        k2, k3 = st.columns(2)
        with k2:
            st.markdown("##### Status Batch Inventaris")
            n = ev["status"].value_counts()
            data = pd.DataFrame({"Status": list(n.index), "Jumlah": list(n.values)})
            fig = px.pie(data, names="Status", values="Jumlah", hole=0.6, color="Status",
                         color_discrete_map=cfg.STATUS_WARNA)
            fig.update_traces(textinfo="value", hovertemplate="%{label}: %{value} batch<extra></extra>")
            ui.tampil_grafik(fig, "dash_status")
        with k3:
            st.markdown("##### Distribusi Masa Simpan Estimasi")
            numerik = ev[ev["tengah_hari"].notna() & (ev["tengah_hari"] > 0)]
            if numerik.empty:
                ui.empty_state("Belum ada data", "Tidak ada bahan dengan acuan masa simpan numerik.")
            else:
                fig_h = ui.hist_log_hari(numerik, "tengah_hari", "Jumlah batch", nbins=min(8, max(4, len(numerik))))
                ui.tampil_grafik(fig_h, "dash_hist")

        st.markdown("##### Batch yang Mendekati atau Melewati Batas Konsumsi (FEFO)")
        dekat = ev[ev["status"].isin([cfg.SEGERA, cfg.KRITIS])]
        if dekat.empty:
            ui.callout("Tidak ada batch yang mendekati atau melewati batas estimasi.", "ok")
        else:
            t = tables.tabel_prioritas(dekat).drop(columns=["FIFO"], errors="ignore")
            ui.tampil_df(ui.warnai_status(t), hide_index=True)

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=True, mode_manual=False)
