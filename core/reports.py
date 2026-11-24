"""Pembuatan laporan CSV dan PDF (mencakup inventaris FEFO, rencana pengadaan, simulasi, asumsi, dan sitasi dataset)."""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import config as cfg
from ui import components as ui
from ui import tables


def csv_inventaris(ev: pd.DataFrame) -> bytes:
    """CSV lengkap hasil evaluasi inventaris FEFO (UTF-8 BOM agar terbuka benar di Excel)."""
    fefo_col = ev["urutan_fefo"] if "urutan_fefo" in ev.columns else ev["urutan_fifo"]
    waste_col = ev["estimasi_busuk_kg"] if "estimasi_busuk_kg" in ev.columns else 0.0
    d = pd.DataFrame({
        "Prioritas": ev["urutan_prioritas"], "Nama bahan": ev["nama"],
        "Item": ev["item"] if "item" in ev.columns else "", "Kategori": ev["kategori"],
        "Jumlah": ev["jumlah"], "Satuan": ev["satuan"], "Lokasi": ev["lokasi"], "Suhu (C)": ev["suhu_c"],
        "Tanggal diterima": ev["tanggal_diterima"].dt.date, "Umur (hari)": ev["umur_hari"],
        "Acuan masa simpan": ev["rentang_teks"], "Batas konsumsi estimasi": ev["tanggal_estimasi"],
        "Tanggal kedaluwarsa aktual": ev["tanggal_kedaluwarsa_aktual"].dt.date, "Sisa hari": ev["sisa_efektif"],
        "Status": ev["status"], "Urutan FEFO": fefo_col, "Estimasi Terbuang (kg)": waste_col,
        **{f"P melewati masa simpan <= {h} hari": ev[f"p{h}"].round(4) for h in cfg.HORIZON_HARI},
        "Rekomendasi": ev["rekomendasi"], "Catatan estimasi": ev["catatan_estimasi"]})
    return d.to_csv(index=False).encode("utf-8-sig")


def csv_rencana_pengadaan(df_rencana: pd.DataFrame) -> bytes:
    """CSV rencana pengadaan mingguan per item (termasuk kolom sumber='data'/'asumsi')."""
    return df_rencana.to_csv(index=False).encode("utf-8-sig")


def csv_statistik(desk: pd.DataFrame) -> bytes:
    return desk.to_csv(index=False).encode("utf-8-sig")


def _tabel(df: pd.DataFrame, lebar: list[float], st_kolom: str | None = "Status") -> Table:
    sel = ParagraphStyle("sel", fontName="Helvetica", fontSize=8, leading=10)
    kepala = ParagraphStyle("kep", parent=sel, fontName="Helvetica-Bold", textColor=colors.white)
    data = [[Paragraph(str(c), kepala) for c in df.columns]]
    for _, r in df.iterrows():
        data.append([Paragraph("—" if pd.isna(v) else str(v), sel) for v in r.values])
    t = Table(data, colWidths=[w * cm for w in lebar], repeatRows=1)
    gaya = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")])]
    if st_kolom and st_kolom in df.columns:
        j = list(df.columns).index(st_kolom)
        for i, v in enumerate(df[st_kolom], start=1):
            gaya.append(("BACKGROUND", (j, i), (j, i), colors.HexColor(cfg.STATUS_LATAR.get(v, "#FFFFFF"))))
    t.setStyle(TableStyle(gaya))
    return t


def pdf_laporan(
    ev: pd.DataFrame,
    desk: pd.DataFrame,
    meta_hist: dict | None = None,
    df_rencana: pd.DataFrame | None = None,
    df_simulasi: pd.DataFrame | None = None,
    gram_per_porsi: dict[str, float] | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Laporan Ketersediaan Bahan Baku, Pengadaan, dan Masa Simpan")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=colors.HexColor("#111827"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, textColor=colors.HexColor("#111827"))
    p = ParagraphStyle("p", parent=ss["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11)
    kecil = ParagraphStyle("k", parent=p, fontSize=7.5, textColor=colors.HexColor("#6B7280"))

    s = [Paragraph("Laporan Sistem Ketersediaan Bahan Baku (Supply Chain) & Masa Simpan", h1),
         Paragraph(f"Dibuat pada {ui.tanggal(datetime.now())} · Sumber: USDA FoodKeeper & Mendeley Data (CC BY 4.0)", kecil),
         Spacer(1, 5)]

    n = ev["status"].value_counts() if not ev.empty else pd.Series(dtype=int)
    tinggi = int((ev[f"p{cfg.RISIKO_TINGGI_HORIZON}"] >= cfg.RISIKO_TINGGI_AMBANG).sum()) if len(ev) else 0
    est_waste = float(ev["estimasi_busuk_kg"].sum()) if ("estimasi_busuk_kg" in ev.columns and len(ev)) else 0.0
    s.append(Paragraph("1. Ringkasan Inventaris & Estimasi Barang Terbuang (FEFO)", h2))
    ring = pd.DataFrame([{
        "Total batch": len(ev), "Aman": int(n.get(cfg.AMAN, 0)),
        "Segera Dikonsumsi": int(n.get(cfg.SEGERA, 0)), "Kritis": int(n.get(cfg.KRITIS, 0)),
        "Berisiko tinggi (3 hr)": tinggi, "Est. Terbuang FEFO (kg)": ui.angka(est_waste, 2),
    }])
    s.append(_tabel(ring, [3.5, 3, 4, 3, 4.5, 5], None))

    if df_rencana is not None and not df_rencana.empty:
        s.append(Paragraph("2. Rencana Pengadaan Mingguan (Safety Stock, ROP & Batas Masa Simpan)", h2))
        d_r = df_rencana.copy()
        for c in d_r.columns:
            if d_r[c].dtype.kind == "f":
                d_r[c] = d_r[c].map(lambda x: ui.angka(x, 2))
        lebar_r = [25.0 / max(1, len(d_r.columns))] * len(d_r.columns)
        s.append(_tabel(d_r, lebar_r, None))

    if df_simulasi is not None and not df_simulasi.empty:
        s.append(Paragraph("3. Evaluasi & Simulasi Kebijakan Persediaan (Trade-off Layanan vs Barang Terbuang)", h2))
        d_s = df_simulasi.copy()
        for c in d_s.columns:
            if d_s[c].dtype.kind == "f":
                d_s[c] = d_s[c].map(lambda x: ui.angka(x, 2))
        lebar_s = [25.0 / max(1, len(d_s.columns))] * len(d_s.columns)
        s.append(_tabel(d_s, lebar_s, None))

    if len(ev):
        s.append(Paragraph("4. Prioritas Konsumsi Batch (FEFO — First-Expired, First-Out)", h2))
        pri = tables.tabel_prioritas(ev).drop(columns=["FIFO"], errors="ignore")
        pri["Diterima"] = pri["Diterima"].astype(str)
        pri["Sisa (hari)"] = pri["Sisa (hari)"].map(lambda x: "—" if pd.isna(x) else int(x))
        s.append(_tabel(pri, [1.6, 4.2, 2.4, 2.6, 1.8, 3.6, 1.4, 8.2]))

    if len(desk):
        s.append(Paragraph("5. Statistik Deskriptif Masa Simpan Dataset Acuan (hari)", h2))
        d = desk.copy()
        for c in d.columns:
            if d[c].dtype.kind == "f":
                d[c] = d[c].map(lambda x: ui.angka(x, 1))
        lebar_desk = [2.6, 1.1, 1.9, 1.6, 1.8, 1.5, 1.5, 1.5, 2.3, 2.1, 1.7, 1.4, 1.6][:len(d.columns)]
        s.append(_tabel(d, lebar_desk, None))

    gmap = gram_per_porsi or cfg.GRAM_PER_PORSI
    teks_gram = ", ".join(f"{k}: {int(v)} g/porsi" for k, v in gmap.items())
    s.append(Paragraph("6. Transparansi Asumsi, Keterbatasan & Sitasi Dataset", h2))
    s.append(Paragraph(
        f"• <b>Konversi menggunakan asumsi gram per porsi:</b> {teks_gram}.<br/>"
        "• <b>Keterbatasan Data:</b> Data permintaan berasal dari restoran di Stuttgart, Jerman (760 hari, 2013–2015). "
        "Indeks musiman bulanan hanya didasarkan pada ±2 tahun data (indikatif) dan tidak mencakup efek hari besar di Indonesia tanpa faktor event manual. "
        "Bahan bermode manual menggunakan parameter asumsi pengguna (default CV = 0,30).<br/>"
        f"• <b>Sitasi Permintaan:</b> {cfg.SITASI_MENDELEY}<br/>"
        f"• <b>Sitasi Masa Simpan:</b> {cfg.SITASI_USDA}", p))
    s.append(Spacer(1, 4))
    s.append(Paragraph(cfg.DISCLAIMER, kecil))
    doc.build(s)
    return buf.getvalue()
