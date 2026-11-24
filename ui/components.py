"""Komponen UI yang dapat dipakai ulang di semua halaman."""
from __future__ import annotations

import html
from datetime import date, datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as cfg

BADGE_CLS = {cfg.AMAN: "b-aman", cfg.SEGERA: "b-segera", cfg.KRITIS: "b-kritis", cfg.BELUM: "b-belum"}
TONE = {"aman": "t-aman", "segera": "t-segera", "kritis": "t-kritis", "info": "t-info", "": ""}
PALET = ["#2563EB", "#0891B2", "#7C3AED", "#DB2777", "#65A30D", "#EA580C", "#475569"]


# ---------- format ----------
def angka(x, nd: int = 1) -> str:
    """Format angka gaya Indonesia: 1.234,5"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    s = f"{x:,.{nd}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def persen(x, nd: int = 0) -> str:
    return "—" if x is None or pd.isna(x) else angka(x * 100, nd) + "%"


def tanggal(d) -> str:
    if d is None or d is pd.NaT or (not isinstance(d, (date, datetime)) and pd.isna(d)):
        return "—"
    d = pd.Timestamp(d)
    if pd.isna(d):
        return "—"
    return f"{d.day} {cfg.BULAN_ID[d.month - 1]} {d.year}"


def hari_teks(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{angka(x, 0 if float(x).is_integer() else 1)} hari"


# ---------- layout ----------
def page_header(judul: str, sub: str = "") -> None:
    st.markdown(f"<div class='page-title'>{html.escape(judul)}</div><div class='page-sub'>{html.escape(sub)}</div>",
                unsafe_allow_html=True)


def kpi_grid(items: list[dict]) -> None:
    """items: dict(label, value, hint='', tone='')."""
    kartu = "".join(
        f"<div class='kpi {TONE.get(i.get('tone', ''), '')}'><div class='lbl'>{html.escape(i['label'])}</div>"
        f"<div class='val'>{html.escape(str(i['value']))}</div>"
        f"<div class='hint'>{html.escape(i.get('hint', ''))}</div></div>" for i in items)
    st.markdown(f"<div class='kpi-grid'>{kartu}</div>", unsafe_allow_html=True)


def badge(status: str) -> str:
    return f"<span class='badge {BADGE_CLS.get(status, 'b-belum')}'>{html.escape(status)}</span>"


def lencana_sumber(sumber: str) -> str:
    """Lencana pembeda hasil berbasis data Mendeley vs asumsi manual pengguna."""
    if str(sumber).lower() in ("asumsi", "manual", "asumsi pengguna"):
        return "<span class='badge b-segera'>Berbasis asumsi pengguna</span>"
    return "<span class='badge b-aman'>Berbasis data</span>"


def kotak_asumsi(tampilkan_mendeley: bool = True, mode_manual: bool = False) -> None:
    """Kotak transparansi asumsi & keterbatasan data yang wajib tampil di semua halaman."""
    from database import db
    gmap = db.peta_gram_per_porsi()
    teks_gram = ", ".join(f"{k.title()}: {int(v)} g/porsi" for k, v in gmap.items() if k in cfg.GRAM_PER_PORSI)
    poin_manual = (
        "<br>• <b>Mode Manual (Asumsi Pengguna):</b> Parameter rata-rata pemakaian dan koefisien variasi (CV) diisi pengguna "
        "(default CV = 0,30 diturunkan dari variasi permintaan daging pada dataset restoran); hasil perencanaan bersifat ilustrasi, bukan analisis data."
        if mode_manual else ""
    )
    teks = (
        f"<b>Transparansi Asumsi & Keterbatasan Data:</b><br>"
        f"• <b>Konversi menggunakan asumsi gram per porsi:</b> {teks_gram} (dataset asli hanya memuat satuan porsi).<br>"
        f"• <b>Sumber & Keterbatasan Dataset Permintaan:</b> Data permintaan berasal dari restoran di Stuttgart, Jerman "
        f"(4 Okt 2013 – 7 Nov 2015, 760 hari; ±2 tahun sehingga indeks musiman bulanan bersifat indikatif dan tidak memuat efek Ramadan/Lebaran tanpa faktor event manual). "
        f"Harga, biaya, dan lead time pemasok adalah parameter konfigurasi/simulasi."
        f"{poin_manual}"
        + (f"<br>• <b>Sitasi:</b> {html.escape(cfg.SITASI_MENDELEY)}" if tampilkan_mendeley else "")
    )
    callout(teks, "info")


def callout(teks: str, jenis: str = "info") -> None:
    st.markdown(f"<div class='callout c-{jenis}'>{teks}</div>", unsafe_allow_html=True)


def empty_state(judul: str, teks: str) -> None:
    st.markdown(f"<div class='empty'><b>{html.escape(judul)}</b>{html.escape(teks)}</div>", unsafe_allow_html=True)


def disclaimer() -> None:
    callout(cfg.DISCLAIMER, "warn")


def link_halaman(kunci: str, label: str, icon: str | None = None) -> None:
    """Tautan cepat ke halaman lain (hanya bila navigasi terdaftar)."""
    import nav
    page = nav.PAGES.get(kunci)
    if page is not None:
        st.page_link(page, label=label, icon=icon)


# ---------- tabel & grafik ----------
def tampil_df(df, **kw) -> object:
    """st.dataframe lebar penuh; kompatibel dengan API lama dan baru Streamlit."""
    try:
        return st.dataframe(df, width="stretch", **kw)
    except TypeError:
        return st.dataframe(df, use_container_width=True, **kw)


def tampil_grafik(fig: go.Figure, key: str | None = None) -> None:
    fig.update_layout(font_family="Inter, sans-serif", font_color="#111827", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=-0.3, x=0))
    fig.update_xaxes(gridcolor="#EEF0F3", zeroline=False)
    fig.update_yaxes(gridcolor="#EEF0F3", zeroline=False)
    cfgp = {"displaylogo": False, "displayModeBar": "hover", "responsive": True}
    try:
        st.plotly_chart(fig, width="stretch", key=key, config=cfgp)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, key=key, config=cfgp)


def hist_log_hari(df: pd.DataFrame, kol_x: str, judul_y: str, color_col: str | None = None,
                  nbins: int = 12, satuan_obj: str = "bahan") -> go.Figure:
    """Histogram berskala log10 yang di-bin secara eksplisit agar tidak gagal render di Plotly.js."""
    d = df[df[kol_x] > 0].copy()
    lx_all = np.log10(d[kol_x].astype(float))
    lo, hi = float(lx_all.min()), float(lx_all.max())
    if np.isclose(lo, hi):
        lo, hi = lo - 0.15, hi + 0.15
    edges = np.linspace(lo, hi, nbins + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    lebar = (edges[1] - edges[0]) * 0.9
    rentang_lbl = [f"{angka(10 ** edges[i], 1)}–{angka(10 ** edges[i + 1], 1)} hari" for i in range(nbins)]

    fig = go.Figure()
    if color_col and color_col in d:
        groups = [(str(k), g) for k, g in d.groupby(color_col)]
    else:
        groups = [("", d)]

    for i, (nama, g) in enumerate(groups):
        cnt, _ = np.histogram(np.log10(g[kol_x].astype(float)), bins=edges)
        fig.add_bar(
            x=mids, y=cnt, width=lebar, name=nama,
            marker_color=PALET[i % len(PALET)],
            opacity=0.65 if color_col else 1.0,
            customdata=rentang_lbl,
            hovertemplate=(f"<b>{nama}</b><br>" if nama else "") + "%{customdata}: %{y} " + satuan_obj + "<extra></extra>",
        )

    patokan = [0.1, 0.5, 1, 2, 3, 7, 14, 30, 90, 180, 365, 1000, 3650]
    ticks = [t for t in patokan if lo - 0.2 <= np.log10(t) <= hi + 0.15]
    if len(ticks) < 3:
        ticks = [round(10 ** v, 1) for v in np.linspace(lo, hi, 4)]
    ticktext = [angka(t, 0 if float(t).is_integer() else 1) for t in ticks]

    fig.update_layout(
        barmode="overlay" if color_col else "relative",
        xaxis=dict(title="Estimasi masa simpan (hari, skala log)", tickvals=[np.log10(t) for t in ticks], ticktext=ticktext),
        yaxis=dict(title=judul_y, dtick=1 if d.shape[0] <= 15 else None),
        showlegend=bool(color_col),
    )
    return fig


def warnai_status(df: pd.DataFrame, kolom: str = "Status"):
    """Styler pandas: warna latar sel status (hijau/kuning/merah)."""
    def f(v):
        return (f"background-color:{cfg.STATUS_LATAR.get(v, '#fff')};color:{cfg.STATUS_WARNA.get(v, '#111')};"
                "font-weight:600")
    return df.style.map(f, subset=[kolom])
