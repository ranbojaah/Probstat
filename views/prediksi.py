"""Halaman Prediksi Masa Simpan."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from core import cache
from core import historical as hist_mod
from core import reference as ref
from core import shelf_life as sl
from core import stats
from database import db
from ui import components as ui


def _panel_km(r: pd.Series) -> None:
    st.markdown("#### Berdasarkan data historis Anda (Estimator Kaplan-Meier)")
    hist = cache.get_historis()
    if hist.empty:
        ui.callout("Belum ada data historis. Unggah data observasi di halaman <b>Dataset</b>, catat bahan <i>Habis/Busuk</i> "
                   "di halaman <b>Inventaris Bahan</b>, atau klik tombol di bawah untuk memuat data contoh.", "info")
        if st.button("Muat data historis contoh (simulasi)", key="pred_muat_hist", icon=":material/science:"):
            df_c = hist_mod.buat_contoh_historis()
            db.simpan_historis(df_c, "contoh_observasi_historis.csv", len(df_c), "{}")
            st.rerun()
        return
    g, ket = stats.pilih_kelompok_km(hist, r["lokasi"])
    if g is None:
        ui.callout(f"Data historis memiliki kurang dari {cfg.MIN_KEJADIAN_KM} kejadian pembusukan, sehingga estimasi "
                   "survival tidak dijustifikasi secara statistik dan tidak ditampilkan.", "warn")
        return
    d, e = g["durasi_hari"].values, g["kejadian"].values
    umur = float(r["umur_hari"])
    st.caption(f"Sumber: {ket} (n = {len(g)}, kejadian = {int(g['kejadian'].sum())}). Umur bahan saat ini: {int(umur)} hari.")
    if umur > d.max():
        ui.callout("Umur bahan melebihi durasi pengamatan terpanjang pada data historis, sehingga probabilitas tidak dapat dihitung.", "warn")
        return
    with st.spinner("Menghitung interval kepercayaan (bootstrap)…"):
        hasil = stats.peluang_km_ci(d, e, umur)
    cols = st.columns(len(hasil))
    for c, (_, h) in zip(cols, hasil.iterrows()):
        if np.isnan(h["p"]):
            c.metric(f"≤ {int(h['horizon'])} hari", "—", help="Melebihi rentang pengamatan data historis.")
        else:
            ci = f"CI 95%: {ui.persen(h['ci_bawah'])}–{ui.persen(h['ci_atas'])}" if not np.isnan(h["ci_bawah"]) else "CI tidak tersedia"
            c.metric(f"≤ {int(h['horizon'])} hari", ui.persen(h["p"]), ci, delta_color="off")
    kmf = stats.km_fit(d, e)
    ci = kmf.confidence_interval_
    fig = go.Figure()
    fig.add_scatter(x=kmf.timeline, y=kmf.survival_function_.iloc[:, 0], mode="lines", line_shape="hv", name="Probabilitas bertahan", line_color="#2563EB")
    fig.add_scatter(x=ci.index, y=ci.iloc[:, 1], mode="lines", line_shape="hv", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=ci.index, y=ci.iloc[:, 0], mode="lines", line_shape="hv", line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(37,99,235,.15)", name="CI 95%", hoverinfo="skip")
    fig.add_vline(x=umur, line_dash="dash", line_color="#6B7280", annotation_text="Umur saat ini")
    fig.update_layout(xaxis_title="Hari sejak diterima", yaxis_title="Probabilitas belum rusak", yaxis_range=[0, 1.02])
    ui.tampil_grafik(fig, "km_pred")
    st.caption("Probabilitas dihitung bersyarat: peluang rusak dalam N hari ke depan, mengingat bahan masih baik pada umur saat ini. "
               "Interval kepercayaan memakai bootstrap persentil (300 ulangan).")
    with st.expander("Lihat rumus Estimator Kaplan-Meier & Bootstrap CI"):
        st.markdown("**1. Fungsi Survival Empiris Kaplan-Meier:**")
        st.latex(r"\hat{S}(t) = \prod_{i:\, t_i \le t} \left(1 - \frac{d_i}{n_i}\right)")
        st.caption("$t_i$ = waktu terjadinya pembusukan, $d_i$ = jumlah bahan yang busuk pada waktu $t_i$, "
                   "$n_i$ = jumlah bahan yang masih berisiko (belum busuk dan belum tersensor) sesaat sebelum $t_i$.")
        st.markdown("**2. Probabilitas Bersyarat Melewati Masa Simpan dalam $h$ Hari:**")
        st.latex(r"\hat{P}(t_0 < T \le t_0 + h \mid T > t_0) = 1 - \frac{\hat{S}(t_0 + h)}{\hat{S}(t_0)}")
        st.markdown("**3. Interval Kepercayaan Bootstrap Persentil 95%:** Sampel ditarik ulang dengan pengembalian sebanyak "
                    f"$B = {cfg.BOOTSTRAP_ULANG}$ kali, lalu diambil persentil ke-2,5 dan ke-97,5 dari distribusi hasil bootstrap.")


def render() -> None:
    ui.page_header("Prediksi Masa Simpan", "Estimasi sisa masa simpan dan probabilitas melewati batas untuk bahan pilihan Anda.")
    ev = cache.get_evaluasi()
    if ev.empty:
        ui.empty_state("Belum ada bahan untuk diprediksi", "Tambahkan bahan di halaman Inventaris Bahan terlebih dahulu.")
        ui.link_halaman("inventaris", "Buka Inventaris Bahan", ":material/inventory_2:")
        return

    ev = ev.sort_values("urutan_prioritas")
    opsi = {int(r["id"]): f"{r['nama']} · {r['lokasi']} · diterima {ui.tanggal(r['tanggal_diterima'])}" for _, r in ev.iterrows()}
    pilih = st.selectbox("Pilih bahan dari inventaris", list(opsi), format_func=lambda i: opsi[i])
    r = ev[ev["id"] == pilih].iloc[0]

    st.markdown(f"### {r['nama']} &nbsp; {ui.badge(r['status'])}", unsafe_allow_html=True)
    st.caption(f"Produk acuan: {r['produk_acuan']} · {r['kategori']} · {r['lokasi']}")

    numerik = r["jenis"] in ref.JENIS_NUMERIK
    c = st.columns(4)
    c[0].metric("Estimasi masa simpan", ui.hari_teks(r["tengah_hari"]) if numerik else "—", r["rentang_teks"], delta_color="off")
    c[1].metric("Umur saat ini", ui.hari_teks(r["umur_hari"]))
    c[2].metric("Sisa hari (estimasi)", ui.hari_teks(r["sisa_hari"]) if numerik else "—")
    c[3].metric("Batas konsumsi (estimasi)", ui.tanggal(r["tanggal_estimasi"]) if numerik else "—")

    if pd.notna(r["tanggal_kedaluwarsa_aktual"]):
        ui.callout(f"<b>Tanggal kedaluwarsa aktual (kemasan):</b> {ui.tanggal(r['tanggal_kedaluwarsa_aktual'])}. "
                   "Tanggal ini berasal dari produsen dan <b>berbeda</b> dari estimasi dataset di atas. Status memakai yang lebih awal.", "info")
    if r["catatan_estimasi"]:
        ui.callout(r["catatan_estimasi"], "warn")
    if r["tips"]:
        st.caption(f"Tips dataset: {r['tips']}")

    if numerik:
        st.markdown("#### Probabilitas melewati masa simpan")
        cols = st.columns(len(cfg.HORIZON_HARI))
        for col, h in zip(cols, cfg.HORIZON_HARI):
            col.metric(f"Dalam {h} hari", ui.persen(r[f"p{h}"]))

        mn, mx = r["min_hari"], r["maks_hari"]
        tmax = max(mx * 1.3, r["umur_hari"] * 1.2, 3)
        t, s = sl.kurva_bertahan(mn, mx, tmax)
        fig = go.Figure()
        fig.add_scatter(x=t, y=s, mode="lines", line_shape="hv" if mx <= mn else "linear", name="Probabilitas belum melewati batas", line_color="#2563EB")
        if mx > mn:
            fig.add_vrect(x0=mn, x1=mx, fillcolor="rgba(217,119,6,.12)", line_width=0, annotation_text="Rentang acuan", annotation_position="top left")
        fig.add_vline(x=r["umur_hari"], line_dash="dash", line_color="#6B7280", annotation_text="Umur saat ini")
        fig.update_layout(xaxis_title="Hari sejak diterima", yaxis_title="Probabilitas belum melewati batas", yaxis_range=[0, 1.02])
        ui.tampil_grafik(fig, "kurva_pred")

        with st.expander("Rumus & Perhitungan Matematis (Distribusi Seragam & Probabilitas Bersyarat)", expanded=True):
            umur_val = float(r["umur_hari"])
            mid_val = float(r["tengah_hari"])
            st.markdown("**1. Estimasi Tengah & Sisa Masa Simpan:**")
            st.latex(rf"\mu = \frac{{a_{{\min}} + b_{{\max}}}}{{2}} = \frac{{{ui.angka(mn, 1)} + {ui.angka(mx, 1)}}}{{2}} = {ui.angka(mid_val, 1)}\text{{ hari}}, "
                     rf"\qquad \text{{Batas}} = \lceil \mu \rceil = {int(np.ceil(mid_val))}\text{{ hari}}, "
                     rf"\qquad \text{{Sisa}} = {int(np.ceil(mid_val))} - {int(umur_val)} = {int(r['sisa_hari'])}\text{{ hari}}")
            if r["jenis"] == ref.JENIS_RENTANG:
                st.markdown(
                    f"**2. Fungsi Distribusi Kumulatif (CDF) Seragam Kontinu** $T \\sim \\text{{Uniform}}({ui.angka(mn, 1)},\\; {ui.angka(mx, 1)})$:"
                )
                st.latex(r"F(t) = \text{clip}\!\left(\frac{t - a_{\min}}{b_{\max} - a_{\min}},\; 0,\; 1\right), \qquad S(t) = 1 - F(t)")
                st.markdown("**3. Rumus Probabilitas Bersyarat (Conditional Probability):**\n"
                            "Peluang bahan melewati masa simpan dalam $h$ hari ke depan, dengan syarat masih bertahan pada umur saat ini $a$:")
                st.latex(r"P(a < T \le a + h \mid T > a) = \frac{F(a + h) - F(a)}{1 - F(a)}")
                fa = sl.cdf_seragam(umur_val, mn, mx)
                rincian = []
                for h in cfg.HORIZON_HARI:
                    fh = sl.cdf_seragam(umur_val + h, mn, mx)
                    p_val = sl.peluang_lewat(umur_val, mn, mx, h)
                    rumus_str = "1 (sudah melewati batas atas)" if fa >= 1.0 else f"({fh:.3f} - {fa:.3f}) / (1 - {fa:.3f})"
                    rincian.append({
                        "Horizon (h)": f"{h} hari",
                        "Umur + h (a+h)": f"{umur_val + h:g} hari",
                        "F(a)": round(fa, 3),
                        "F(a+h)": round(fh, 3),
                        "Substitusi Rumus": rumus_str,
                        "Probabilitas P": ui.persen(p_val, 1),
                    })
                st.markdown(f"**4. Hasil Substitusi Angka untuk {r['nama']}** ($a = {umur_val:g}$ hari, $a_{{\\min}} = {mn:g}$, $b_{{\\max}} = {mx:g}$):")
                ui.tampil_df(pd.DataFrame(rincian), hide_index=True)
                st.caption("Catatan: Interval kepercayaan tidak ditampilkan pada bagian ini karena dataset acuan FoodKeeper hanya memuat "
                           "rentang panduan [min, maks], bukan sampel pengamatan individual.")
            else:
                st.markdown(
                    f"Dataset hanya memberi satu nilai acuan tunggal (**{r['rentang_teks']}**, $a_{{\\min}} = b_{{\\max}} = {mn:g}$ hari) tanpa rentang. "
                    "Secara matematis fungsi langkah bernilai $F(t) = 0$ untuk $t < b_{\\max}$ dan $F(t) = 1$ untuk $t \\ge b_{\\max}$, "
                    "sehingga probabilitas bernilai 0% sebelum batas dan 100% setelah mencapainya.")
            st.markdown(f"**Aturan Klasifikasi Status ({r['status']}):** *Kritis* jika $a \\ge \\lceil \\mu \\rceil$; "
                        f"*Segera Dikonsumsi* jika $a \\ge \\lceil a_{{\\min}} \\rceil$, sisa $\\le {int(cfg.SEGERA_FRAKSI * 100)}\\%\\,\\mu$, atau "
                        f"$P(h={cfg.RISIKO_TINGGI_HORIZON}) \\ge {int(cfg.RISIKO_TINGGI_AMBANG * 100)}\\%$; selain itu *Aman*.")
        st.divider()
        if not cache.get_historis().empty:
            _panel_km(r)
        else:
            with st.expander("Analisis Survival Empiris (Kaplan-Meier — aktif bila data historis pembusukan tersedia)"):
                _panel_km(r)
    else:
        ui.callout("Prediksi probabilitas tidak tersedia karena dataset tidak memuat angka masa simpan untuk kombinasi ini. "
                   "Isi tanggal kedaluwarsa aktual dari kemasan agar status dapat ditentukan.", "warn")
    ui.kotak_asumsi(tampilkan_mendeley=False)
    ui.disclaimer()
