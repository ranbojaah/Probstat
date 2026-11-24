"""Pembentuk tabel tampilan (nama kolom Indonesia) dari hasil evaluasi inventaris (FEFO)."""
from __future__ import annotations

import pandas as pd

import config as cfg
from ui import components as ui


def tabel_tampil(ev: pd.DataFrame) -> pd.DataFrame:
    if ev.empty:
        return pd.DataFrame()
    fefo_col = ev["urutan_fefo"] if "urutan_fefo" in ev.columns else ev["urutan_fifo"]
    waste_col = ev["estimasi_busuk_kg"] if "estimasi_busuk_kg" in ev.columns else pd.Series(0.0, index=ev.index)
    item_col = ev["item"].fillna("—") if "item" in ev.columns else pd.Series("—", index=ev.index)
    t = pd.DataFrame({
        "id": ev["id"],
        "Nama bahan": ev["nama"],
        "Item": item_col,
        "Kategori": ev["kategori"],
        "Jumlah": [f"{ui.angka(j, 2).rstrip('0').rstrip(',')} {s}" for j, s in zip(ev["jumlah"], ev["satuan"])],
        "Lokasi": ev["lokasi"],
        "Suhu (°C)": ev["suhu_c"],
        "Diterima": ev["tanggal_diterima"].map(ui.tanggal),
        "Umur (hari)": ev["umur_hari"],
        "Acuan masa simpan": ev["rentang_teks"],
        "Batas konsumsi (estimasi)": ev["tanggal_estimasi"].map(ui.tanggal),
        "Kedaluwarsa (aktual)": ev["tanggal_kedaluwarsa_aktual"].map(ui.tanggal),
        "Sisa (hari)": ev["sisa_efektif"],
        "FEFO": fefo_col,
        "Est. Terbuang (kg)": waste_col.round(2),
        "Status": ev["status"],
    })
    return t


def tabel_prioritas(ev: pd.DataFrame, n: int | None = None) -> pd.DataFrame:
    d = ev.sort_values("urutan_prioritas")
    if n:
        d = d.head(n)
    fefo_col = d["urutan_fefo"] if "urutan_fefo" in d.columns else d["urutan_fifo"]
    return pd.DataFrame({
        "Prioritas": d["urutan_prioritas"], "Nama bahan": d["nama"], "Lokasi": d["lokasi"],
        "Diterima": d["tanggal_diterima"].map(ui.tanggal), "Sisa (hari)": d["sisa_efektif"],
        "Status": d["status"], "FEFO": fefo_col, "FIFO": d["urutan_fifo"], "Rekomendasi": d["rekomendasi"]})


def tabel_risiko(ev: pd.DataFrame, n: int = 10, horizon: int = 7) -> pd.DataFrame:
    d = ev.dropna(subset=[f"p{horizon}"]).sort_values([f"p{horizon}", "umur_hari"], ascending=False).head(n)
    out = pd.DataFrame({"Nama bahan": d["nama"], "Lokasi": d["lokasi"], "Status": d["status"],
                        "Umur (hari)": d["umur_hari"]})
    for h in cfg.HORIZON_HARI:
        out[f"P ≤ {h} hari"] = d[f"p{h}"].map(lambda x: ui.persen(x, 0))
    return out
