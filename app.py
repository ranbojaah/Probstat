"""Titik masuk aplikasi Smart Food Inventory & Supply Chain.

Jalankan dengan:  streamlit run app.py
"""
import streamlit as st

import config as cfg
import nav
from database import db
from ui.styles import inject_css
from views import (
    dashboard,
    dataset,
    inventaris,
    laporan,
    pemasok,
    pengadaan,
    permintaan,
    prediksi,
    simulasi,
    statistik,
)

st.set_page_config(page_title=f"{cfg.APP_NAME}", page_icon=":material/eco:", layout="wide", initial_sidebar_state="auto")
db.init_db()
inject_css()
st.logo(str(cfg.BASE_DIR / "assets" / "logo.svg"), size="large")

nav.PAGES = {
    "dashboard": st.Page(dashboard.render, title="Dashboard Ketersediaan", icon=":material/dashboard:", url_path="dashboard", default=True),
    "inventaris": st.Page(inventaris.render, title="Inventaris Bahan (FEFO)", icon=":material/inventory_2:", url_path="inventaris"),
    "permintaan": st.Page(permintaan.render, title="Permintaan & Peramalan", icon=":material/trending_up:", url_path="permintaan"),
    "pengadaan": st.Page(pengadaan.render, title="Perencanaan Pengadaan", icon=":material/shopping_cart_checkout:", url_path="pengadaan"),
    "simulasi": st.Page(simulasi.render, title="Simulasi & Evaluasi", icon=":material/science:", url_path="simulasi"),
    "pemasok": st.Page(pemasok.render, title="Pemasok", icon=":material/local_shipping:", url_path="pemasok"),
    "prediksi": st.Page(prediksi.render, title="Prediksi Masa Simpan", icon=":material/schedule:", url_path="prediksi"),
    "statistik": st.Page(statistik.render, title="Analisis Statistik", icon=":material/monitoring:", url_path="statistik"),
    "dataset": st.Page(dataset.render, title="Dataset", icon=":material/database:", url_path="dataset"),
    "laporan": st.Page(laporan.render, title="Laporan", icon=":material/description:", url_path="laporan"),
}
halaman = st.navigation(list(nav.PAGES.values()))
st.sidebar.caption("Estimasi masa simpan bersifat perkiraan dan bukan jaminan keamanan pangan.")
halaman.run()
