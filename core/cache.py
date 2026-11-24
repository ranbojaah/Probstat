"""Pemuat data berbasis cache Streamlit (satu-satunya modul core yang memakai Streamlit)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import permintaan as perm_mod
from core import reference as ref
from core import shelf_life as sl
from database import db


@st.cache_data(show_spinner=False)
def _muat_ref(token: tuple):
    produk, kategori = ref.load_reference()
    return produk, kategori, ref.build_shelf_life_table(produk)


def get_reference():
    return _muat_ref(ref.reference_token())


def hapus_cache_referensi() -> None:
    _muat_ref.clear()


def get_permintaan_kg() -> pd.DataFrame:
    df = db.muat_permintaan_db()
    if df.empty:
        return df
    return perm_mod.ke_kg(df, db.peta_gram_per_porsi())


def get_rata_permintaan_kg() -> dict[str, float]:
    df = get_permintaan_kg()
    out: dict[str, float] = {}
    if not df.empty:
        for c in [col for col in df.columns if col.endswith("_kg")]:
            out[c[:-3]] = float(df[c].mean())
    for _, r in db.daftar_parameter_item().iterrows():
        it = str(r["item"])
        if r["mode_permintaan"] == "manual" and pd.notna(r["mean_manual_kg_hari"]):
            out[it] = float(r["mean_manual_kg_hari"])
    return out


def get_evaluasi() -> pd.DataFrame:
    produk, _, tabel = get_reference()
    fc_map = get_rata_permintaan_kg()
    return sl.evaluasi_inventaris(db.daftar_inventaris(), tabel, produk, forecast_harian=fc_map)


def get_historis() -> pd.DataFrame:
    return db.muat_historis()
