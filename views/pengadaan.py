"""Halaman Perencanaan Pengadaan (Halaman Inti): Mode Data & Manual, Safety Stock (Normal vs Empiris), ROP, Batas Masa Simpan, Kalender Restok Bulanan, dan Newsvendor."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as cfg
from core import cache
from core import permintaan as perm_mod
from core import procurement as proc
from core import shelf_life as sl
from database import db
from ui import components as ui


def render() -> None:
    ui.page_header(
        "Perencanaan Pengadaan",
        "Hitung Safety Stock (Normal & Kuantil Empiris), Reorder Point (ROP), Batas Stok Masa Simpan, dan Kebutuhan Restok Bulanan.",
    )
    if "notif_pengadaan" in st.session_state:
        st.success(st.session_state.pop("notif_pengadaan"))

    produk, _, tabel_ref = cache.get_reference()
    df_kg = cache.get_permintaan_kg()
    peta_pid = db.peta_item_ke_produk_id()
    label_prod = dict(zip(produk["produk_id"], produk["label"]))

    # Daftar bahan: 4 item data + daging total + seluruh 661 produk FoodKeeper
    opsi_utama = [
        ("ayam", f"Ayam — {label_prod.get(peta_pid.get('ayam', 118), 'Chicken')} [Mode Data]"),
        ("lamm", f"Domba (Lamb) — {label_prod.get(peta_pid.get('lamm', 51), 'Lamb')} [Mode Data]"),
        ("steak", f"Daging Sapi (Steak) — {label_prod.get(peta_pid.get('steak', 40), 'Beef steaks')} [Mode Data]"),
        ("koefte", f"Daging Giling (Koefte) — {label_prod.get(peta_pid.get('koefte', 43), 'Beef ground')} [Mode Data]"),
        ("daging", "Daging Total (Lamb + Steak + Koefte) [Mode Data]"),
    ]
    # Tambahkan item kustom dari parameter_item atau produk FoodKeeper
    param_db = db.daftar_parameter_item()
    item_ada = {k for k, _ in opsi_utama}
    for _, r in param_db.iterrows():
        it = str(r["item"])
        if it not in item_ada:
            mode_lbl = "Mode Data" if r["mode_permintaan"] == "data" and f"{it}_kg" in df_kg.columns else "Mode Manual - Asumsi"
            opsi_utama.append((it, f"{it.title()} [{mode_lbl}]"))
            item_ada.add(it)

    for _, r in produk.iterrows():
        pid = int(r["produk_id"])
        kunci = f"fk_{pid}"
        if pid not in peta_pid.values():
            opsi_utama.append((kunci, f"{r['label']} · {r['kategori']} [Mode Manual - Asumsi]"))

    peta_label_opsi = dict(opsi_utama)
    pilihan = st.selectbox("Pilih bahan baku (Item Data Restoran atau 661 Produk FoodKeeper)",
                           [k for k, _ in opsi_utama], format_func=lambda k: peta_label_opsi[k])

    # Tentukan produk_id dan apakah bahan punya data permintaan nyata
    if pilihan.startswith("fk_"):
        pid_aktif = int(pilihan.split("_")[1])
        item_kode = label_prod[pid_aktif].split(" (")[0].lower()
        cfg_item = db.get_parameter_item(item_kode)
    else:
        item_kode = pilihan
        cfg_item = db.get_parameter_item(item_kode)
        pid_aktif = int(cfg_item["produk_id"]) if (cfg_item and pd.notna(cfg_item.get("produk_id"))) else peta_pid.get(item_kode, 40)

    kol_kg = f"{item_kode}_kg"
    punya_data = (not df_kg.empty) and (kol_kg in df_kg.columns) and (
        item_kode in ("ayam", "lamm", "steak", "koefte", "daging")
        or (cfg_item is not None and cfg_item.get("mode_permintaan") == "data")
    )
    mode_manual = not punya_data
    sumber_mode = "asumsi" if mode_manual else "data"

    st.markdown(
        f"**Mode Perencanaan:** {ui.lencana_sumber(sumber_mode)} &nbsp; "
        + ("<span class='badge b-segera'>Konversi menggunakan asumsi gram per porsi</span>" if not mode_manual else ""),
        unsafe_allow_html=True,
    )

    info_sup = db.info_pemasok_untuk_item(item_kode)
    c1, c2, c3, c4 = st.columns(4)
    lokasi = c1.selectbox("Lokasi penyimpanan", list(cfg.LOKASI), index=1)
    info_ms = sl.masa_simpan_produk(tabel_ref, pid_aktif, lokasi)
    ms_default = float(info_ms["min_hari"]) if pd.notna(info_ms["min_hari"]) and info_ms["min_hari"] > 0 else 2.0
    masa_simpan = c2.number_input(
        f"Masa simpan konservatif (hari, acuan: {info_ms['rentang_teks']})",
        min_value=0.5, max_value=365.0, value=float(ms_default), step=0.5,
        help="Diambil otomatis dari batas bawah (konservatif) dataset USDA FoodKeeper untuk lokasi terpilih.",
    )
    layanan_pct = c3.slider("Target tingkat layanan (Cycle Service Level %)", min_value=80, max_value=99,
                            value=int(round(float((cfg_item or {}).get("tingkat_layanan", 0.95)) * 100)), step=1)
    tingkat_layanan = layanan_pct / 100.0
    L_hari = c4.number_input(f"Lead time pemasok L (hari, {info_sup['nama_pemasok']})",
                             min_value=0.5, max_value=30.0, value=float(info_sup["lead_time_rata"]), step=0.5)

    c5, c6, c7, c8 = st.columns(4)
    std_L = c5.number_input("Simpangan baku lead time s_L (hari)", min_value=0.0, max_value=10.0,
                            value=float(info_sup["lead_time_std"]), step=0.1)
    R_hari = c6.number_input("Periode tinjau ulang R (hari)", min_value=0.5, max_value=14.0, value=1.0, step=0.5)
    stok_db, pipe_db = db.stok_dan_pipeline_kg(item_kode, lokasi=lokasi)
    stok_sekarang = c7.number_input("Stok tersedia saat ini I (kg)", min_value=0.0, value=float(stok_db), step=0.5)
    pipeline_kg = c8.number_input("Pesanan dalam perjalanan I_pipeline (kg)", min_value=0.0, value=float(pipe_db), step=0.5)

    profil_pinjam = None
    if mode_manual:
        ui.callout(
            "<b>Mode Input Manual (Bahan Tanpa Riwayat Permintaan):</b> Masukkan rata-rata pemakaian harian dan koefisien variasi (CV). "
            "Seluruh hasil di bawah wajib dibaca sebagai <b>Berbasis asumsi pengguna</b>, bukan hasil analisis data.",
            "warn",
        )
        m1, m2, m3 = st.columns([1.2, 1.5, 1.5])
        mean_manual = m1.number_input(
            "Rata-rata pemakaian harian (kg/hari)", min_value=0.0,
            value=float((cfg_item or {}).get("mean_manual_kg_hari") or 4.0), step=0.5,
        )
        cv_manual = m2.slider(
            "Koefisien variasi (CV = s / mean)", min_value=0.10, max_value=0.60,
            value=float(np.clip(float((cfg_item or {}).get("cv_manual") or cfg.CV_DEFAULT_MANUAL), 0.10, 0.60)), step=0.01,
            help="Default dari variasi permintaan daging pada dataset restoran (CV ayam 0,26–0,36; daging 0,19–0,29); ganti dengan nilai yang sesuai kondisi Anda.",
        )
        st.caption("Keterangan CV: *Default 0,30 diturunkan dari variasi permintaan daging pada dataset restoran; ganti dengan nilai yang sesuai kondisi Anda.*")
        pakai_prof = m3.checkbox(
            "Pakai profil hari dari data daging",
            value=bool((cfg_item or {}).get("pakai_profil_hari", 0)),
            help="Jika dicentang, rasio ramai akhir pekan dipinjam dari dataset restoran (asumsi).",
        )
        if pakai_prof and not df_kg.empty:
            profil_pinjam = perm_mod.profil_hari_rasio(df_kg, "daging_porsi")
            st.markdown("<span class='badge b-segera'>Profil hari dipinjam dari dataset restoran (asumsi)</span>", unsafe_allow_html=True)
        if st.button("Simpan parameter manual bahan ini", icon=":material/save:"):
            db.simpan_parameter_item(
                item_kode, pid_aktif, gram_per_porsi=200.0, tingkat_layanan=tingkat_layanan,
                mode_permintaan="manual", mean_manual_kg_hari=mean_manual, cv_manual=cv_manual,
                pakai_profil_hari=int(pakai_prof),
            )
            st.session_state["notif_pengadaan"] = f"Parameter manual untuk '{item_kode}' disimpan."
            st.rerun()

        param_hari = proc.parameter_manual(mean_manual, cv=cv_manual, profil_hari=profil_pinjam)
        res_rasio = None
    else:
        param_hari = proc.parameter_per_hari(df_kg, kol_kg)
        res_rasio = proc.rasio_residual_harian(df_kg, kol_kg)

    tbl_minggu, info_p = proc.tabel_perencanaan_mingguan(
        param_hari, L_hari=L_hari, R_hari=R_hari, tingkat_layanan=tingkat_layanan,
        masa_simpan_hari=masa_simpan, std_L=std_L, residual_rasio=res_rasio,
        stok_sekarang=stok_sekarang, pipeline_kg=pipeline_kg, moq_kg=float(info_sup["moq_kg"]),
    )

    for w in info_p["peringatan"]:
        ui.callout(f"<b>Peringatan Batas Masa Simpan:</b> {w}", "warn")

    st.markdown(f"##### Tabel Parameter & Rencana Pengadaan per Hari dalam Minggu &nbsp; {ui.lencana_sumber(sumber_mode)}",
                unsafe_allow_html=True)
    tampil_m = tbl_minggu.drop(columns=["hari"]).copy()
    tampil_m["Layanan Efektif"] = (tampil_m["Layanan Efektif"] * 100.0).round(1)
    tampil_m = tampil_m.rename(columns={"Layanan Efektif": "Layanan Efektif (%)", "sumber": "Sumber"})
    fmt_m = {c: st.column_config.NumberColumn(format="%.2f")
             for c in ["Mean (kg)", "Std (kg)", "SS Normal (kg)", "SS Empiris (kg)", "ROP (kg)",
                       "Target Stok S (kg)", "Stok Maks S_cap (kg)", "Jumlah Pesan q (kg)"]}
    fmt_m["Layanan Efektif (%)"] = st.column_config.NumberColumn(format="%.1f%%")
    ui.tampil_df(tampil_m, hide_index=True, column_config=fmt_m)

    # Grafik perbandingan Stok, ROP, Target S, dan Batas Masa Simpan S_cap per hari
    fig_p = go.Figure()
    fig_p.add_bar(x=tbl_minggu["Hari"], y=tbl_minggu["Mean (kg)"], name="Rata-rata Permintaan (kg)", marker_color="#93C5FD")
    fig_p.add_scatter(x=tbl_minggu["Hari"], y=tbl_minggu["ROP (kg)"], mode="lines+markers", name="Reorder Point (ROP)", line_color="#2563EB")
    fig_p.add_scatter(x=tbl_minggu["Hari"], y=tbl_minggu["Target Stok S (kg)"], mode="lines+markers", name="Target Stok S (L+R)", line_color="#7C3AED")
    fig_p.add_scatter(x=tbl_minggu["Hari"], y=tbl_minggu["Stok Maks S_cap (kg)"], mode="lines+markers",
                      name="Batas Masa Simpan (S_cap)", line=dict(color="#DC2626", dash="dash"))
    fig_p.update_layout(xaxis_title="Hari dalam minggu", yaxis_title="Kilogram (kg)")
    ui.tampil_grafik(fig_p, "pengadaan_grafik")

    # Tombol buat pesanan pembelian untuk hari pilihan
    cp1, cp2, cp3 = st.columns([1.5, 1.2, 2])
    hari_pesan = cp1.selectbox("Pilih hari pemesanan", tbl_minggu["Hari"].tolist(), index=5)
    baris_h = tbl_minggu[tbl_minggu["Hari"] == hari_pesan].iloc[0]
    qty_saran = float(baris_h["Jumlah Pesan q (kg)"])
    qty_pesan = cp2.number_input("Jumlah dipesan (kg)", min_value=0.0, value=round(qty_saran, 2), step=0.5)
    if cp3.button(f"Buat pesanan ke {info_sup['nama_pemasok']}", type="primary", icon=":material/shopping_cart:", disabled=qty_pesan <= 0):
        pid_order = db.buat_pesanan(item_kode, qty_pesan, pemasok_id=info_sup["pemasok_id"])
        st.session_state["notif_pengadaan"] = f"Pesanan #{pid_order} ({qty_pesan:.2f} kg {item_kode}) dibuat. Terima pesanan di halaman Inventaris Bahan."
        st.rerun()

    st.divider()
    col_kiri, col_kanan = st.columns(2)

    with col_kiri:
        st.markdown(f"##### Kalender Restok Bulanan (30 Hari) &nbsp; {ui.lencana_sumber(sumber_mode)}", unsafe_allow_html=True)
        faktor_ev_bln = st.number_input("Faktor event bulanan (mis. 1,20 untuk bulan Ramadan/Desember)",
                                        min_value=0.5, max_value=3.0, value=1.0, step=0.05)
        rata_harian_total = float(param_hari["mean"].mean())
        if not mode_manual:
            tbl_idx, _ = perm_mod.indeks_musiman_bulanan(df_kg, kol_kg)
            kal_baris = []
            for _, rb in tbl_idx.iterrows():
                idx_m = float(rb["Indeks Musiman"])
                butuh_30 = rata_harian_total * 30.0 * idx_m * faktor_ev_bln
                frek = int(np.ceil(30.0 / max(1.0, masa_simpan)))
                kal_baris.append({
                    "Bulan": rb["Bulan"],
                    "Indeks Musiman": round(idx_m, 2),
                    "Faktor Event": round(faktor_ev_bln, 2),
                    "Estimasi Kebutuhan (kg/bulan)": round(butuh_30, 1),
                    "Min. Frekuensi Kirim/Bulan": f"{frek}× kirim (@ ≤ {masa_simpan:g} hr)",
                    "Sumber": "data" if faktor_ev_bln == 1.0 else "data + asumsi event",
                })
            ui.tampil_df(pd.DataFrame(kal_baris), hide_index=True)
            st.caption("Catatan: Indeks musiman bulanan dihitung dari ±2 tahun data restoran dan bersifat indikatif.")
        else:
            butuh_manual_30 = rata_harian_total * 30.0 * faktor_ev_bln
            frek = int(np.ceil(30.0 / max(1.0, masa_simpan)))
            ui.callout(
                f"<b>Mode Manual (Tanpa Indeks Musiman Bulanan):</b> Kebutuhan datar 30 hari = "
                f"<b>{ui.angka(butuh_manual_30, 1)} kg/bulan</b> ({ui.angka(rata_harian_total * faktor_ev_bln, 2)} kg/hari × 30 hari), "
                f"minimal <b>{frek}× pengiriman/bulan</b> agar tidak melewati masa simpan {masa_simpan:g} hari.",
                "warn",
            )

    with col_kanan:
        st.markdown(f"##### Model Newsvendor (Satu Periode Perishable) &nbsp; {ui.lencana_sumber(sumber_mode)}", unsafe_allow_html=True)
        nv1, nv2 = st.columns(2)
        cu_val = nv1.number_input("Biaya kurang stok Cu (Rp/kg)", min_value=1000.0,
                                  value=float((cfg_item or {}).get("biaya_kurang_per_kg") or 60000.0), step=5000.0)
        co_val = nv2.number_input("Biaya barang busuk Co (Rp/kg)", min_value=1000.0,
                                  value=float((cfg_item or {}).get("biaya_lebih_per_kg") or 40000.0), step=5000.0)
        nv = proc.newsvendor(float(baris_h["Mean (kg)"]), float(baris_h["Std (kg)"]), cu_val, co_val)
        nvk1, nvk2, nvk3 = st.columns(3)
        nvk1.metric("Critical Ratio (CR)", f"{nv['CR'] * 100:.1f}%")
        nvk2.metric("Skor-z (z_CR)", f"{nv['z_CR']:.3f}")
        nvk3.metric(f"Kuantitas Optimal Q* ({hari_pesan})", f"{ui.angka(nv['Q_star'], 2)} kg")
        st.caption("Model Newsvendor menyeimbangkan biaya kehilangan penjualan ($C_u$) terhadap biaya bahan terbuang busuk ($C_o$) pada satu siklus.")

    with st.expander("Rumus Matematis & Substitusi Angka (Hari Terpilih: " + hari_pesan + ")", expanded=True):
        mh = float(baris_h["Mean (kg)"])
        sh = float(baris_h["Std (kg)"])
        z_v = info_p["z"]
        ss_v = float(baris_h["SS Normal (kg)"])
        rop_v = float(baris_h["ROP (kg)"])
        s_v = float(baris_h["Target Stok S (kg)"])
        scap_v = float(baris_h["Stok Maks S_cap (kg)"])
        q_v = float(baris_h["Jumlah Pesan q (kg)"])

        st.markdown("**1. Safety Stock (Normal & Lead Time Acak):**")
        st.latex(rf"SS = z\sqrt{{L\,s_h^2 + \bar{{d}}_h^2\,s_L^2}} = {z_v:.3f}\sqrt{{{L_hari:g}({sh:.2f})^2 + ({mh:.2f})^2({std_L:g})^2}} = {ss_v:.2f}\text{{ kg}}")
        st.markdown("**2. Reorder Point (Titik Pemesanan Ulang):**")
        st.latex(rf"ROP = \bar{{d}}_h L + SS = ({mh:.2f} \times {L_hari:g}) + {ss_v:.2f} = {rop_v:.2f}\text{{ kg}}")
        st.markdown("**3. Target Stok Periodic Review ($S$) & Batas Masa Simpan ($S_{cap}$):**")
        st.latex(rf"S = \sum_{{t=1}}^{{L+R}}\hat{{d}}_t + z\,s_h\sqrt{{L+R}} = {s_v:.2f}\text{{ kg}}, \qquad "
                 rf"S_{{cap}} = \sum_{{t=1}}^{{m={masa_simpan:g}}}\hat{{d}}_t = {scap_v:.2f}\text{{ kg}}")
        st.markdown("**4. Kuantitas Pesan ($q$) & Model Newsvendor ($Q^*$):**")
        st.latex(rf"q = \max\bigl(0,\ \min(S, S_{{cap}}) - I - I_{{pipeline}}\bigr) = "
                 rf"\max\bigl(0,\ \min({s_v:.2f}, {scap_v:.2f}) - {stok_sekarang:.2f} - {pipeline_kg:.2f}\bigr) = {q_v:.2f}\text{{ kg}}")
        st.latex(rf"CR = \frac{{C_u}}{{C_u + C_o}} = \frac{{{cu_val:,.0f}}}{{{cu_val:,.0f} + {co_val:,.0f}}} = {nv['CR']:.3f}, \qquad "
                 rf"Q^* = \bar{{d}}_h + z_{{CR}}\,s_h = {mh:.2f} + ({nv['z_CR']:.3f})({sh:.2f}) = {nv['Q_star']:.2f}\text{{ kg}}")

    st.divider()
    ui.kotak_asumsi(tampilkan_mendeley=True, mode_manual=mode_manual)
