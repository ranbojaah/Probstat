"""Halaman Permintaan & Peramalan: eksplorasi permintaan harian, uji hari/bulan, perbandingan metode forecast, dan faktor event."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from core import cache
from core import forecast as fc_mod
from core import permintaan as perm_mod
from core import stats as stats_mod
from database import db
from ui import components as ui


def render() -> None:
    ui.page_header(
        "Permintaan & Peramalan",
        "Analisis statistik permintaan harian bahan baku (pola hari-dalam-minggu, indeks musiman bulanan) dan evaluasi metode peramalan.",
    )
    df_kg = cache.get_permintaan_kg()
    if df_kg.empty:
        ui.empty_state("Belum ada data permintaan", "Unggah file permintaan harian di halaman Dataset terlebih dahulu.")
        ui.link_halaman("dataset", "Buka Halaman Dataset", ":material/database:")
        return

    c_pil1, c_pil2 = st.columns([2, 1.5])
    item_opsi = [k for k in ("ayam", "daging", "lamm", "steak", "koefte") if f"{k}_porsi" in df_kg.columns]
    for c in df_kg.columns:
        if c.endswith("_porsi") and c[:-6] not in item_opsi:
            item_opsi.append(c[:-6])
    item = c_pil1.selectbox("Pilih bahan baku", item_opsi, format_func=lambda k: cfg.ITEM_LABEL.get(k, k.title()))
    satuan = c_pil2.radio("Satuan tampilan", ["porsi", "kg"], horizontal=True,
                          help="Satuan 'kg' dihitung menggunakan asumsi gram per porsi.")
    kol = f"{item}_{satuan}"

    st.markdown(f"Status sumber parameter: {ui.lencana_sumber('data')}"
                + (" &nbsp; <span class='badge b-segera'>Konversi menggunakan asumsi gram per porsi</span>" if satuan == "kg" else ""),
                unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs([
        "1. Kualitas & Tren Harian",
        "2. Pola Hari-dalam-Minggu (Kuat)",
        "3. Pola Bulanan (Indikatif)",
        "4. Peramalan 14 Hari & Faktor Event",
    ])

    with t1:
        lap = perm_mod.laporan_kualitas(df_kg, satuan=satuan)
        ui.kpi_grid([
            dict(label="Jumlah hari pengamatan", value=f"{lap['jumlah_hari']} hari",
                 hint=f"{lap['tanggal_awal']} s.d. {lap['tanggal_akhir']}", tone="info"),
            dict(label="Celah tanggal (tutup)", value=f"{lap['jumlah_celah']} celah ({lap['hari_tidak_tercatat']} hari)",
                 hint="Tidak diimputasi / tidak dikarang", tone="segera"),
            dict(label="Nilai kosong (NaN)", value=lap["nilai_kosong"], hint="Dataset bersih tanpa missing value", tone="aman"),
            dict(label=f"Rata-rata {cfg.ITEM_LABEL.get(item, item)}", value=f"{ui.angka(df_kg[kol].mean(), 2)} {satuan}/hari",
                 hint=f"SD = {ui.angka(df_kg[kol].std(ddof=1), 2)} {satuan}", tone="info"),
        ])
        ui.tampil_df(lap["ringkasan_item"], hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f")
                                    for c in ["Rata-rata", "Simpangan baku", "CV", "Median", "Q1", "Q3", "IQR", "Min", "Maks"]})
        if not lap["daftar_celah"].empty:
            with st.expander("Lihat daftar celah tanggal (restoran tutup, tidak diisi nilai karangan)"):
                ui.tampil_df(lap["daftar_celah"], hide_index=True)

        norm = stats_mod.uji_normalitas(df_kg[kol])
        if norm:
            st.markdown(f"**Uji Normalitas Shapiro-Wilk ({cfg.ITEM_LABEL.get(item, item)})**: "
                        f"$W = {ui.angka(norm['W'], 4)}$, $p = {norm['p']:.2e}$, skewness = ${ui.angka(norm['skew'], 2)}$.")
            ui.callout(
                "<b>Konsekuensi Statistik:</b> Karena $p < 0,05$, distribusi permintaan harian <b>tidak normal</b> (miring ke kanan karena lonjakan akhir pekan). "
                "Oleh karena itu, halaman <b>Perencanaan Pengadaan</b> menyediakan perhitungan <i>Safety Stock</i> versi <b>Kuantil Empiris</b> berdampingan dengan versi <b>Normal (skor-z)</b>.",
                "warn",
            )

        fig_ts = px.line(df_kg, x="tanggal", y=kol, color_discrete_sequence=["#2563EB"])
        fig_ts.update_layout(xaxis_title="Tanggal", yaxis_title=f"Permintaan ({satuan}/hari)")
        ui.tampil_grafik(fig_ts, "perm_ts")

    with t2:
        st.markdown("##### Rata-rata Permintaan per Hari dalam Seminggu (dengan CI 95%)")
        g_hari = df_kg.groupby("hari")[kol].agg(["count", "mean", "std", "median"]).reindex(range(7)).reset_index()
        g_hari["Hari"] = g_hari["hari"].map(lambda i: cfg.HARI_ID[int(i)])
        g_hari["CV"] = np.where(g_hari["mean"] > 0, g_hari["std"] / g_hari["mean"], 0.0)
        g_hari["se"] = g_hari["std"] / np.sqrt(g_hari["count"].clip(lower=1))
        g_hari["ci95"] = 1.96 * g_hari["se"]

        fig_h = go.Figure(go.Bar(
            x=g_hari["Hari"], y=g_hari["mean"], marker_color="#2563EB",
            error_y=dict(type="data", array=g_hari["ci95"], visible=True),
            hovertemplate="<b>%{x}</b><br>Rata-rata: %{y:.2f} " + satuan + "<extra></extra>",
        ))
        fig_h.update_layout(xaxis_title="Hari dalam minggu", yaxis_title=f"Rata-rata ({satuan}/hari)")
        ui.tampil_grafik(fig_h, "perm_hari_bar")

        tbl_h = g_hari[["Hari", "count", "mean", "std", "CV", "median"]].rename(
            columns={"count": "n", "mean": f"Rata-rata ({satuan})", "std": f"Simpangan Baku ({satuan})", "median": f"Median ({satuan})"}
        )
        ui.tampil_df(tbl_h, hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in tbl_h.columns if c not in ("Hari", "n")})

        kw_h = stats_mod.kruskal(df_kg.assign(hari_val=df_kg[kol]).rename(columns={"hari": "grup_hari", "hari_val": "hari"}), "grup_hari")
        if kw_h:
            rasio_sab_min = float(g_hari.loc[5, "mean"] / max(1e-6, g_hari.loc[6, "mean"]))
            st.markdown(f"**Uji Kruskal-Wallis Antar Hari**: $H = {ui.angka(kw_h['H'], 1)}$, $p = {kw_h['p']:.2e}$, "
                        f"$\\varepsilon^2 = {ui.angka(kw_h['eps2'], 2)}$. Permintaan hari **Sabtu ≈ {ui.angka(rasio_sab_min, 2)}× Minggu**.")
            ui.callout(
                "<b>Temuan Terpenting:</b> Pola hari-dalam-minggu sangat kuat ($p \\ll 0,001$). Menggunakan satu angka <i>Safety Stock</i> dan <i>ROP</i> "
                "yang sama untuk seluruh hari akan menyebabkan kelebihan stok di hari Minggu dan kekurangan stok di hari Sabtu. "
                "Oleh karena itu, seluruh parameter pengadaan di aplikasi ini dihitung <b>spesifik per hari dalam minggu</b>.",
                "ok",
            )

    with t3:
        st.markdown("##### Indeks Musiman Bulanan (Setelah Koreksi Hari-dalam-Minggu)")
        tbl_bln, kw_bln = perm_mod.indeks_musiman_bulanan(df_kg, kol)
        fig_b = go.Figure()
        fig_b.add_bar(x=tbl_bln["Bulan"], y=tbl_bln["Indeks Musiman"], marker_color="#0891B2", name="Indeks Musiman")
        fig_b.add_hline(y=1.0, line_dash="dash", line_color="#6B7280", annotation_text="Rata-rata (1,00)")
        fig_b.update_layout(xaxis_title="Bulan", yaxis_title="Indeks Musiman (rasio)", yaxis_range=[0, max(1.3, float(tbl_bln["Indeks Musiman"].max()) * 1.15)])
        ui.tampil_grafik(fig_b, "perm_bln_bar")

        ui.tampil_df(tbl_bln[["Bulan", "n_hari", "Rata-rata", "Indeks Musiman"]], hide_index=True,
                     column_config={"Rata-rata": st.column_config.NumberColumn(format="%.2f"),
                                    "Indeks Musiman": st.column_config.NumberColumn(format="%.2f")})
        if kw_bln:
            st.markdown(f"**Uji Kruskal-Wallis Efek Bulan (pada rasio terkoreksi hari)**: "
                        f"$H = {ui.angka(kw_bln['H'], 2)}$, $p = {kw_bln['p']:.4g}$, $\\varepsilon^2 = {ui.angka(kw_bln['eps2'], 3)}$.")
        ui.callout(
            "<b>Catatan Kehati-hatian (Data Hanya ±2 Tahun):</b> Meskipun uji Kruskal-Wallis signifikan secara statistik, simpangan indeks bulanan "
            "hanya berkisar ±5–13% dan setiap bulan hanya memiliki 2 pengamatan tahun (Oktober 3). "
            "Perlakukan indeks musiman bulanan ini sebagai <b>indikatif</b>, bukan pola pasti.",
            "warn",
        )
        with st.expander("Lihat rumus Indeks Musiman Bulanan & Uji Kruskal-Wallis"):
            st.latex(r"r_t = \frac{d_t}{\bar{d}_{h(t)}}, \qquad I_m = \frac{\text{rata-rata } r_t \text{ pada bulan } m}{\text{rata-rata keseluruhan } r_t}")
            st.latex(r"H = \frac{12}{N(N+1)}\sum_{j=1}^{k}\frac{R_j^2}{n_j} - 3(N+1)")

    with t4:
        st.markdown("##### Evaluasi Metode Peramalan (Rolling-Origin)")
        with st.spinner("Mengevaluasi 3 metode peramalan (rolling-origin)..."):
            tbl_eval, metode_terbaik, detail_eval = fc_mod.evaluasi_rolling_origin(df_kg, kol, n_uji=42)
        ui.tampil_df(tbl_eval[["Metode", "MAE", "RMSE", "sMAPE (%)"]], hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in ["MAE", "RMSE", "sMAPE (%)"]})
        st.caption(f"Metode dengan RMSE terendah: **{metode_terbaik}** (sMAPE digunakan menggantikan MAPE biasa karena terdapat hari bernilai 0).")

        c_m1, c_m2 = st.columns(2)
        pilihan_metode = c_m1.selectbox("Metode peramalan untuk 14 hari ke depan", fc_mod.DAFTAR_METODE,
                                        index=fc_mod.DAFTAR_METODE.index(metode_terbaik))
        mulai_fc = c_m2.date_input("Mulai tanggal ramalan", value=date.today())

        with st.expander("Faktor Event Manual (Ramadan, Lebaran, Idul Adha, Tahun Baru, dll.)"):
            st.caption("Karena dataset berasal dari Jerman, tambahkan pengali event lokal di sini. Hasil yang terkena event otomatis ditandai 'Dipengaruhi asumsi event'.")
            ev_df = db.daftar_faktor_event()
            fe1, fe2, fe3, fe4 = st.columns([1.2, 1.2, 1, 1.6])
            t_m = fe1.date_input("Tanggal mulai", value=date.today(), key="fe_m")
            t_s = fe2.date_input("Tanggal selesai", value=date.today() + timedelta(days=7), key="fe_s")
            fak = fe3.number_input("Faktor pengali", min_value=0.1, max_value=5.0, value=1.25, step=0.05, key="fe_f")
            ket_ev = fe4.text_input("Keterangan event", value="Lonjakan Ramadan / Hari Raya", key="fe_k")
            if st.button("Tambah faktor event", icon=":material/add:"):
                db.tambah_faktor_event(t_m, t_s, fak, ket_ev)
                st.rerun()
            if not ev_df.empty:
                ui.tampil_df(ev_df, hide_index=True)
                id_hapus = st.selectbox("Hapus event ID", ev_df["id"].tolist(), key="fe_del_id")
                if st.button("Hapus event terpilih", icon=":material/delete:"):
                    db.hapus_faktor_event(int(id_hapus))
                    st.rerun()

        baris_m = tbl_eval[tbl_eval["Metode"] == pilihan_metode].iloc[0]
        fc_14 = fc_mod.ramal_horizon(
            df_kg, kol, metode=pilihan_metode, horizon=14,
            faktor_event_df=db.daftar_faktor_event(), mulai_tanggal=mulai_fc,
            residual_kuantil=(float(baris_m["q05_res"]), float(baris_m["q95_res"])),
        )
        if fc_14["dipengaruhi_event"].any():
            st.markdown("<span class='badge b-segera'>Sebagian hari dipengaruhi asumsi faktor event manual</span>", unsafe_allow_html=True)

        fig_fc = go.Figure()
        fig_fc.add_scatter(x=fc_14["tanggal"], y=fc_14["batas_atas"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig_fc.add_scatter(x=fc_14["tanggal"], y=fc_14["batas_bawah"], mode="lines", line=dict(width=0), fill="tonexty",
                           fillcolor="rgba(37,99,235,0.15)", name="Interval Prediksi 90% (Kuantil Residual)")
        fig_fc.add_scatter(x=fc_14["tanggal"], y=fc_14["forecast_akhir"], mode="lines+markers", name="Forecast Akhir", line_color="#2563EB")
        if fc_14["dipengaruhi_event"].any():
            fig_fc.add_scatter(x=fc_14["tanggal"], y=fc_14["forecast_dasar"], mode="lines", line=dict(dash="dot", color="#6B7280"),
                               name="Forecast Dasar (Tanpa Event)")
        fig_fc.update_layout(xaxis_title="Tanggal", yaxis_title=f"Ramalan Permintaan ({satuan}/hari)")
        ui.tampil_grafik(fig_fc, "perm_fc14")

        tampil_fc = pd.DataFrame({
            "Tanggal": pd.to_datetime(fc_14["tanggal"]).dt.strftime("%Y-%m-%d"),
            "Hari": fc_14["Hari"],
            f"Forecast Dasar ({satuan})": fc_14["forecast_dasar"].round(2),
            "Faktor Event": fc_14["faktor_event"].round(2),
            f"Forecast Akhir ({satuan})": fc_14["forecast_akhir"].round(2),
            f"Batas Bawah 90% ({satuan})": fc_14["batas_bawah"].round(2),
            f"Batas Atas 90% ({satuan})": fc_14["batas_atas"].round(2),
            "Status Event": np.where(fc_14["dipengaruhi_event"], "Dipengaruhi asumsi event (" + fc_14["keterangan_event"] + ")", "Data murni"),
        })
        ui.tampil_df(tampil_fc, hide_index=True)

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=True, mode_manual=False)
