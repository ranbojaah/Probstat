"""Halaman Pemasok: CRUD master pemasok, parameter lead time & MOQ per bahan, serta daftar pesanan pembelian."""
from __future__ import annotations

import streamlit as st

import config as cfg
from database import db
from ui import components as ui


def render() -> None:
    ui.page_header(
        "Manajemen Pemasok & Pesanan",
        "Kelola lead time rata-rata, variasi pengiriman, keandalan pemasok, harga per kg, dan Minimum Order Quantity (MOQ).",
    )
    if "notif_pemasok" in st.session_state:
        st.success(st.session_state.pop("notif_pemasok"))

    t1, t2, t3 = st.tabs(["1. Master Pemasok", "2. Bahan, Harga & MOQ per Pemasok", "3. Riwayat Pesanan Pembelian"])

    with t1:
        df_p = db.daftar_pemasok()
        ui.tampil_df(df_p.rename(columns={
            "id": "ID", "nama": "Nama Pemasok", "lead_time_rata": "Lead Time Rata-rata (hari)",
            "lead_time_std": "Std Lead Time (hari)", "keandalan": "Keandalan Tepat Waktu (0-1)",
        }), hide_index=True)

        st.markdown("##### Tambah / Ubah Pemasok")
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        nama = c1.text_input("Nama pemasok", placeholder="Mis. CV Unggas Segar Jaya")
        lt_rata = c2.number_input("Lead time rata-rata (hari)", min_value=0.5, max_value=30.0, value=1.0, step=0.5)
        lt_std = c3.number_input("Simpangan baku lead time (hari)", min_value=0.0, max_value=10.0, value=0.2, step=0.1)
        andal = c4.number_input("Keandalan (0,50–1,00)", min_value=0.50, max_value=1.00, value=0.95, step=0.01)
        if st.button("Tambah pemasok baru", type="primary", icon=":material/add:"):
            if not nama.strip():
                st.error("Nama pemasok wajib diisi.")
            else:
                db.tambah_pemasok(nama, lt_rata, lt_std, andal)
                st.session_state["notif_pemasok"] = f"Pemasok '{nama}' berhasil ditambahkan."
                st.rerun()

        if not df_p.empty:
            with st.expander("Hapus pemasok"):
                id_del = st.selectbox("Pilih pemasok yang akan dihapus", df_p["id"].tolist(),
                                      format_func=lambda i: df_p[df_p["id"] == i]["nama"].iloc[0])
                if st.button("Hapus pemasok terpilih", icon=":material/delete:"):
                    db.hapus_pemasok(int(id_del))
                    st.session_state["notif_pemasok"] = "Pemasok dihapus."
                    st.rerun()

    with t2:
        df_pi = db.daftar_pemasok_item()
        ui.tampil_df(df_pi.rename(columns={
            "nama_pemasok": "Pemasok", "item": "Bahan (Item)", "harga_per_kg": "Harga/kg (Rp)",
            "moq_kg": "MOQ (kg)", "lead_time_rata": "Lead Time (hari)", "lead_time_std": "Std Lead Time",
        }), hide_index=True)

        df_p = db.daftar_pemasok()
        if not df_p.empty:
            st.markdown("##### Hubungkan Bahan ke Pemasok")
            k1, k2, k3, k4 = st.columns(4)
            p_id = k1.selectbox("Pemasok", df_p["id"].tolist(),
                                format_func=lambda i: df_p[df_p["id"] == i]["nama"].iloc[0])
            item_k = k2.text_input("Kode item bahan", value="ayam", help="Mis. ayam, lamm, steak, koefte, atau nama bahan lainnya.")
            hrg = k3.number_input("Harga per kg (Rp, asumsi)", min_value=0.0, value=40000.0, step=1000.0)
            moq = k4.number_input("Minimum Order Quantity / MOQ (kg)", min_value=0.0, value=5.0, step=1.0)
            if st.button("Simpan bahan pemasok", type="primary", icon=":material/save:"):
                db.simpan_pemasok_item(int(p_id), item_k, hrg, moq)
                st.session_state["notif_pemasok"] = f"Bahan '{item_k}' disimpan untuk pemasok terpilih."
                st.rerun()

    with t3:
        pes = db.daftar_pesanan()
        if pes.empty:
            ui.empty_state("Belum ada pesanan pembelian", "Buat pesanan dari halaman Perencanaan Pengadaan atau Dashboard.")
        else:
            ui.tampil_df(pes.rename(columns={
                "id": "No. Pesanan", "tanggal_pesan": "Tgl Pesan", "tanggal_datang_estimasi": "Estimasi Tiba",
                "nama_pemasok": "Pemasok", "item": "Item", "jumlah_kg": "Jumlah (kg)", "status": "Status",
            }), hide_index=True)
            dipesan = pes[pes["status"] == "dipesan"]
            if not dipesan.empty:
                c_a, c_b = st.columns(2)
                id_ps = c_a.selectbox("Pilih pesanan berstatus 'dipesan'", dipesan["id"].tolist(),
                                      format_func=lambda i: f"#{i} · {dipesan[dipesan['id'] == i]['item'].iloc[0]} ({dipesan[dipesan['id'] == i]['jumlah_kg'].iloc[0]} kg)")
                if c_b.button("Terima pesanan ke Inventaris (Kulkas)", type="primary", icon=":material/inventory:"):
                    db.terima_pesanan(int(id_ps), lokasi="Kulkas", suhu_c=4.0)
                    st.session_state["notif_pemasok"] = f"Pesanan #{id_ps} diterima dan ditambahkan sebagai batch baru di Inventaris Bahan."
                    st.rerun()

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=False, mode_manual=True)
