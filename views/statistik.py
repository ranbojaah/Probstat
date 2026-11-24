"""Halaman Analisis Statistik."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from core import cache
from core import historical as hist_mod
from core import stats
from database import db
from ui import components as ui

BASIS = {"Estimasi tengah": "tengah_hari", "Batas bawah (konservatif)": "min_hari", "Batas atas": "maks_hari"}


def _tab_deskriptif(num: pd.DataFrame) -> None:
    basis = st.radio("Dasar perhitungan", list(BASIS), horizontal=True, key="basis")
    d = num.copy()
    d["hari"] = d[BASIS[basis]]
    tbl = stats.deskriptif_per_lokasi(d)
    fmt = {c: st.column_config.NumberColumn(format="%.1f")
           for c in ["Rata-rata", "Median", "Q1", "Q3", "IQR", "Simpangan baku", "Min", "Maks"]}
    fmt["Varians"] = st.column_config.NumberColumn(format="%.0f")
    fmt["Skewness"] = st.column_config.NumberColumn(format="%.2f")
    ui.tampil_df(tbl, hide_index=True, column_config=fmt)
    sem = tbl.iloc[0]
    st.caption(f"Satuan: hari (1 bulan = 30 hari, 1 tahun = 365 hari). Data: {sem['n']} kombinasi produk-lokasi yang memiliki angka masa simpan.")
    norm = stats.uji_normalitas(d["hari"])
    if norm:
        normal_ok = norm["p"] >= 0.05
        st.markdown(f"**Uji Normalitas Shapiro-Wilk**: $W = {ui.angka(norm['W'], 4)}$, $p = {norm['p']:.2g}$, "
                    f"kemencengan (*skewness*) $g_1 = {ui.angka(norm['Skewness'] if 'Skewness' in norm else norm['skew'], 2)}$.")
        ui.callout(
            f"<b>Kesimpulan Distribusi:</b> Karena $p {'<' if not normal_ok else '≥'} 0,05$ dan skewness positif tinggi "
            f"({ui.angka(sem['Skewness'], 2)}), distribusi masa simpan <b>tidak berdistribusi normal</b> (miring ke kanan: "
            f"rata-rata {ui.angka(sem['Rata-rata'])} hari jauh di atas median {ui.angka(sem['Median'])} hari). "
            "Oleh sebab itu, ukuran pemusatan & penyebaran yang tepat adalah <b>Median dan IQR</b>, serta pengujian hipotesis "
            "menggunakan <b>uji non-parametrik (Kruskal-Wallis & Wilcoxon)</b>, bukan ANOVA/uji-t.",
            "info",
        )
    with st.expander("Lihat rumus Statistik Deskriptif, Kuartil & Kemencengan"):
        st.latex(r"\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i, \qquad s^2 = \frac{1}{n-1}\sum_{i=1}^{n}(x_i - \bar{x})^2, \qquad s = \sqrt{s^2}")
        st.latex(r"\text{IQR} = Q_3 - Q_1, \qquad g_1 = \frac{n}{(n-1)(n-2)}\sum_{i=1}^{n}\left(\frac{x_i - \bar{x}}{s}\right)^3")
        st.caption("Keterangan: $\\bar{x}$ = rata-rata sampel, $s^2$ = varians sampel, $s$ = simpangan baku, "
                   "$Q_1, Q_3$ = kuartil ke-1 (25%) dan ke-3 (75%), $\\text{IQR}$ = jangkauan interkuartil, $g_1$ = koefisien kemencengan Fisher-Pearson.")
    fig = ui.hist_log_hari(d, "hari", "Jumlah produk", color_col="lokasi", nbins=25, satuan_obj="produk")
    fig.update_layout(xaxis_title="Masa simpan (hari, skala log)", legend_title="Lokasi")
    ui.tampil_grafik(fig, "hist_sl")


def _tab_kategori(num: pd.DataFrame, ev: pd.DataFrame, hist: pd.DataFrame) -> None:
    st.markdown("##### Masa simpan per kategori (dataset acuan)")
    lok = st.selectbox("Lokasi penyimpanan", list(cfg.LOKASI), index=1, key="kat_lok")
    g = num[num["lokasi"] == lok]
    if g.empty:
        ui.empty_state("Data tidak tersedia", "Tidak ada produk dengan angka masa simpan pada lokasi ini.")
    else:
        agg = g.groupby("kategori")["hari"].agg(["median", "mean", "count"]).reset_index().sort_values("median")
        fig = px.bar(agg, x="median", y="kategori", orientation="h", color_discrete_sequence=["#2563EB"],
                     hover_data={"mean": ":.1f", "count": True})
        fig.update_layout(xaxis_title="Median masa simpan (hari)", yaxis_title="", xaxis_type="log")
        ui.tampil_grafik(fig, "kat_med")

    st.markdown("##### Tingkat bahan Kritis per kategori (inventaris Anda)")
    if ev.empty:
        st.caption("Belum ada inventaris.")
    else:
        e = ev[ev["status"] != cfg.BELUM].copy()
        e["kritis"] = e["status"] == cfg.KRITIS
        if e.empty:
            st.caption("Belum ada bahan yang dapat diestimasi.")
        else:
            laju = stats.laju_per_kelompok(e, "kategori", "kritis")
            fig = go.Figure(go.Bar(x=laju["proporsi"] * 100, y=laju["kategori"], orientation="h", marker_color="#DC2626",
                                   error_x=dict(type="data", symmetric=False, array=(laju["ci_atas"] - laju["proporsi"]) * 100,
                                                arrayminus=(laju["proporsi"] - laju["ci_bawah"]) * 100)))
            fig.update_layout(xaxis_title="Bahan Kritis (%), batang galat = CI Wilson 95%", yaxis=dict(autorange="reversed"))
            ui.tampil_grafik(fig, "kat_kritis")
            st.caption("Ini proporsi bahan yang <b>sudah melewati batas estimasi</b> di inventaris Anda, bukan laju pembusukan hasil pengamatan. "
                       "Dengan sedikit bahan per kategori, interval kepercayaan akan lebar.".replace("<b>", "").replace("</b>", ""))

    st.markdown("##### Laju pembusukan teramati per kategori (data historis)")
    if hist.empty or hist["kategori"].isna().all():
        ui.callout("Dataset FoodKeeper tidak memuat kejadian pembusukan, jadi laju pembusukan sebenarnya tidak dapat dihitung darinya. "
                   "Unggah data historis di halaman <b>Dataset</b> atau klik tombol di bawah untuk memuat contoh.", "info")
        if st.button("Muat data historis contoh (simulasi)", key="kat_muat_hist", icon=":material/science:"):
            df_c = hist_mod.buat_contoh_historis()
            db.simpan_historis(df_c, "contoh_observasi_historis.csv", len(df_c), "{}")
            st.rerun()
    else:
        laju = stats.laju_per_kelompok(hist, "kategori", "kejadian")
        fig = go.Figure(go.Bar(x=laju["proporsi"] * 100, y=laju["kategori"], orientation="h", marker_color="#7C3AED",
                               error_x=dict(type="data", symmetric=False, array=(laju["ci_atas"] - laju["proporsi"]) * 100,
                                            arrayminus=(laju["proporsi"] - laju["ci_bawah"]) * 100)))
        fig.update_layout(xaxis_title="Persentase observasi yang rusak (%), CI Wilson 95%", yaxis=dict(autorange="reversed"))
        ui.tampil_grafik(fig, "kat_hist")
        st.caption("Persentase mentah ini tidak memperhitungkan durasi pengamatan yang berbeda. Gunakan tab Survival untuk analisis yang mengoreksi hal itu.")

    with st.expander("Lihat rumus Interval Kepercayaan Proporsi Wilson (Wilson Score CI 95%)"):
        st.latex(r"\hat{p} = \frac{x}{n}, \qquad \text{CI}_{95\%} = \frac{\hat{p} + \frac{z^2}{2n} \pm z\sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}, \quad z = 1{,}96")
        st.caption("Metode Wilson dipilih dibanding metode Wald standar karena tetap akurat meskipun ukuran sampel $n$ kecil atau proporsi $\\hat{p}$ mendekati 0 atau 1.")


def _tab_kondisi(num: pd.DataFrame) -> None:
    fig = px.box(num, x="lokasi", y="tengah_hari", color="lokasi", log_y=True, points=False, color_discrete_sequence=ui.PALET)
    fig.update_layout(xaxis_title="Lokasi penyimpanan", yaxis_title="Estimasi masa simpan (hari, skala log)", showlegend=False)
    ui.tampil_grafik(fig, "box_lok")
    med = num.groupby("lokasi")["hari"].median().round(1)
    st.caption("Median per lokasi: " + " · ".join(f"{k}: {ui.angka(v)} hari" for k, v in med.items()))
    kw = stats.kruskal(num.assign(hari=num["tengah_hari"]), "lokasi")
    if kw:
        sig = kw["p"] < 0.05
        st.markdown(f"**Uji Kruskal-Wallis ($k = {kw['k']}$ kelompok, $N = {kw['n']}$)**: $H = {ui.angka(kw['H'], 2)}$, "
                    f"$p = {kw['p']:.2g}$, ukuran efek $\\varepsilon^2 = {ui.angka(kw['eps2'], 2)}$.")
        ui.callout(("<b>Keputusan ($p < \\alpha = 0,05$ → Tolak $H_0$):</b> Perbedaan masa simpan antar lokasi penyimpanan <b>nyata secara statistik</b>."
                    if sig else
                    "<b>Keputusan ($p \\ge \\alpha = 0,05$ → Gagal Tolak $H_0$):</b> Perbedaan masa simpan antar lokasi <b>tidak terbukti nyata</b> secara statistik."),
                   "ok" if sig else "info")
    wc = stats.wilcoxon_berpasangan(num.assign(hari=num["tengah_hari"]), "Kulkas", "Freezer")
    if wc:
        st.markdown(f"**Uji Peringkat Bertanda Wilcoxon Berpasangan** pada $n = {wc['n']}$ produk yang punya acuan di Kulkas dan Freezer: "
                    f"median Kulkas {ui.angka(wc['median_a'])} hari vs Freezer {ui.angka(wc['median_b'])} hari, $W = {ui.angka(wc['stat'], 1)}$, $p = {wc['p']:.2g}$.")
    with st.expander("Lihat rumus & Hipotesis Uji Kruskal-Wallis dan Wilcoxon"):
        st.markdown("**1. Uji Non-Parametrik Kruskal-Wallis (3 lokasi independen):**\n"
                    "- $H_0$: Distribusi/median masa simpan sama di ketiga lokasi penyimpanan.\n"
                    "- $H_1$: Setidaknya ada satu lokasi penyimpanan yang memiliki masa simpan berbeda ($\alpha = 0{,}05$).")
        st.latex(r"H = \frac{12}{N(N+1)}\sum_{j=1}^{k}\frac{R_j^2}{n_j} - 3(N+1), \qquad \varepsilon^2 = \frac{H - k + 1}{N - k}")
        st.markdown("**2. Uji Peringkat Bertanda Wilcoxon Berpasangan (Kulkas vs Freezer pada produk yang sama):**\n"
                    "- $H_0$: Median selisih masa simpan pasangan produk $d_i = x_{\text{Freezer},i} - x_{\text{Kulkas},i}$ sama dengan nol.\n"
                    "- $H_1$: Median selisih masa simpan tidak sama dengan nol ($\alpha = 0{,}05$).")
        st.latex(r"W = \min\left(\sum_{d_i > 0} \text{rank}(|d_i|),\; \sum_{d_i < 0} \text{rank}(|d_i|)\right)")
    ui.callout("<b>Catatan:</b> perbandingan ini memakai acuan dataset (panduan), bukan eksperimen. Produk yang punya acuan di tiap lokasi berbeda-beda, "
               "jadi hasilnya menggambarkan panduan, bukan efek sebab-akibat suhu.", "warn")


def _tab_survival(hist: pd.DataFrame) -> None:
    if hist.empty:
        ui.empty_state("Data historis belum tersedia",
                       "Analisis Kaplan-Meier dan Cox membutuhkan data observasi (durasi dan kejadian busuk/tersensor). "
                       "Muat data contoh di bawah atau unggah CSV Anda di halaman Dataset.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Muat data historis contoh (72 observasi)", type="primary", key="surv_muat_hist", icon=":material/science:"):
                df_c = hist_mod.buat_contoh_historis()
                db.simpan_historis(df_c, "contoh_observasi_historis.csv", len(df_c), "{}")
                st.rerun()
        with c2:
            ui.link_halaman("dataset", "Buka halaman Dataset (unggah CSV)", ":material/upload_file:")
        return
    ev_n = int(hist["kejadian"].sum())
    st.caption(f"Data historis aktif: {len(hist)} observasi, {ev_n} kejadian, {len(hist) - ev_n} tersensor.")
    if ev_n < cfg.MIN_KEJADIAN_KM:
        ui.callout(f"Kejadian kurang dari {cfg.MIN_KEJADIAN_KM}. Analisis survival tidak dijustifikasi secara statistik.", "warn")
        return
    opsi = ["Semua data"] + [k for k in ("lokasi", "kategori") if hist[k].notna().sum() > 0]
    by = st.selectbox("Bandingkan kurva berdasarkan", opsi, format_func=lambda x: {"lokasi": "Lokasi simpan", "kategori": "Kategori"}.get(x, x))
    fig = go.Figure()
    if by == "Semua data":
        k = stats.km_fit(hist["durasi_hari"], hist["kejadian"])
        _tambah_kurva(fig, k, "Semua data", ui.PALET[0])
    else:
        for i, (nm, g) in enumerate(hist.dropna(subset=[by]).groupby(by)):
            if len(g) >= 5 and g["kejadian"].sum() >= 1:
                _tambah_kurva(fig, stats.km_fit(g["durasi_hari"], g["kejadian"]), str(nm), ui.PALET[i % len(ui.PALET)])
    fig.update_layout(xaxis_title="Hari sejak mulai", yaxis_title="Probabilitas belum rusak", yaxis_range=[0, 1.02])
    ui.tampil_grafik(fig, "km_all")
    if by != "Semua data":
        lr = stats.logrank(hist, by)
        if lr:
            sig_lr = lr["p"] < 0.05
            st.markdown(f"**Uji Log-Rank** ({lr['k']} kelompok): $\\chi^2 = {ui.angka(lr['stat'], 2)}$, $p = {lr['p']:.2g}$ "
                        f"({'berbeda signifikan ($p < 0,05$)' if sig_lr else 'tidak berbeda signifikan ($p \\ge 0,05$)'}).")
    ui.callout("Kurva turun ke bawah seiring waktu: makin rendah, makin besar kemungkinan bahan sudah rusak. Pita warna adalah interval kepercayaan 95%. "
               "Observasi tersensor (belum rusak saat pengamatan berakhir) tetap dihitung.", "info")

    st.markdown("##### Cox Proportional Hazards")
    c1, c2, c3 = st.columns(3)
    pakai_suhu = c1.checkbox("Suhu simpan", value=hist["suhu_c"].notna().mean() > 0.8, disabled=hist["suhu_c"].notna().mean() <= 0.8)
    pakai_lokasi = c2.checkbox("Lokasi simpan", value=hist["lokasi"].nunique() > 1, disabled=hist["lokasi"].nunique() <= 1)
    pakai_kat = c3.checkbox("Kategori", value=False, disabled=hist["kategori"].nunique() <= 1)
    if not (pakai_suhu or pakai_lokasi or pakai_kat):
        st.caption("Pilih minimal satu variabel yang tersedia.")
        return
    hasil = stats.cox_fit(hist, pakai_suhu, pakai_lokasi, pakai_kat)
    if "galat" in hasil:
        ui.callout(hasil["galat"], "warn")
        return
    fmt = {c: st.column_config.NumberColumn(format="%.3f") for c in ["Rasio hazard", "CI 95% bawah", "CI 95% atas", "Nilai p"]}
    ui.tampil_df(hasil["ringkasan"], hide_index=True, column_config=fmt)
    st.caption(f"n = {hasil['n']}, kejadian = {hasil['kejadian']}, concordance = {hasil['concordance']:.3f}"
               + (f", penalizer = {hasil['penalizer']} (dipakai karena model tanpa penalti gagal konvergen)" if hasil["penalizer"] else ""))
    ui.callout("<b>Rasio hazard</b> &gt; 1 berarti risiko rusak lebih cepat naik; &lt; 1 berarti lebih lambat. "
               "Contoh: 1,10 pada suhu = setiap kenaikan 1 °C meningkatkan risiko rusak sekitar 10% pada saat yang sama. "
               "Ini hubungan statistik, bukan bukti sebab-akibat.", "info")
    if hasil.get("ph") is not None and (hasil["ph"]["Nilai p"] < 0.05).any():
        ui.callout("Uji asumsi proportional hazards menunjukkan pelanggaran pada sebagian variabel (p &lt; 0,05). Tafsirkan rasio hazard dengan hati-hati.", "warn")
    with st.expander("Lihat rumus Estimator Kaplan-Meier, Uji Log-Rank & Regresi Cox PH"):
        st.markdown("**1. Estimator Kaplan-Meier (Product-Limit):**")
        st.latex(r"\hat{S}(t) = \prod_{i:\, t_i \le t} \left(1 - \frac{d_i}{n_i}\right)")
        st.markdown("**2. Uji Log-Rank ($H_0: S_1(t) = S_2(t) = \dots = S_k(t)$):**")
        st.latex(r"\chi^2 = \sum_{j=1}^{k} \frac{(O_j - E_j)^2}{V_j}, \qquad E_{ij} = n_{ij}\frac{d_i}{n_i}")
        st.markdown("**3. Regresi Semi-Parametrik Cox Proportional Hazards:**")
        st.latex(r"h(t \mid \mathbf{X}) = h_0(t)\exp(\beta_1 X_1 + \beta_2 X_2 + \dots + \beta_p X_p), \qquad \text{HR}_j = e^{\beta_j}")


def _tambah_kurva(fig, k, nama, warna):
    ci = k.confidence_interval_
    fig.add_scatter(x=k.timeline, y=k.survival_function_.iloc[:, 0], mode="lines", line_shape="hv", name=nama, line_color=warna)
    fig.add_scatter(x=ci.index, y=ci.iloc[:, 1], mode="lines", line_shape="hv", line=dict(width=0), showlegend=False, hoverinfo="skip")
    r, g, b = (int(warna[i:i + 2], 16) for i in (1, 3, 5))
    fig.add_scatter(x=ci.index, y=ci.iloc[:, 0], mode="lines", line_shape="hv", line=dict(width=0), fill="tonexty",
                    fillcolor=f"rgba({r},{g},{b},.14)", showlegend=False, hoverinfo="skip")


def render() -> None:
    ui.page_header("Analisis Statistik", "Penerapan statistik deskriptif, interval kepercayaan, uji hipotesis non-parametrik, dan analisis survival.")
    ui.callout(
        "<b>Sumber data pada tiap tab:</b> "
        "<b>Tab 1 & 3</b> menganalisis panduan dataset acuan USDA FoodKeeper · "
        "<b>Tab 2</b> menggabungkan dataset acuan, inventaris Anda, dan data historis (CI Wilson) · "
        "<b>Tab 4</b> menganalisis data observasi historis (Kaplan-Meier, Log-Rank, Cox PH).",
        "info",
    )
    produk, _, tabel = cache.get_reference()
    num = stats.tabel_numerik(tabel, produk)
    ev = cache.get_evaluasi()
    hist = cache.get_historis()

    if not hist.empty:
        t1, t2, t3, t4 = st.tabs([
            "1. Deskriptif (Dataset Acuan)",
            "2. Per Kategori & CI Wilson",
            "3. Uji Hipotesis Lokasi",
            "4. Survival (Data Historis)",
        ])
        with t1:
            _tab_deskriptif(num)
        with t2:
            _tab_kategori(num, ev, hist)
        with t3:
            _tab_kondisi(num)
        with t4:
            _tab_survival(hist)
    else:
        t1, t2, t3 = st.tabs([
            "1. Deskriptif (Dataset Acuan)",
            "2. Per Kategori & CI Wilson",
            "3. Uji Hipotesis Lokasi",
        ])
        with t1:
            _tab_deskriptif(num)
        with t2:
            _tab_kategori(num, ev, hist)
        with t3:
            _tab_kondisi(num)
        with st.expander("Analisis Survival (Kaplan-Meier, Log-Rank & Cox PH — aktif bila data historis pembusukan tersedia)"):
            _tab_survival(hist)
    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=False)
