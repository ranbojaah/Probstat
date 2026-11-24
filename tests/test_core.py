"""Uji logika inti (tanpa Streamlit): mencakup 14+ spesifikasi perombakan Supply Chain & seluruh tes lama."""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as cfg  # noqa: E402
from core import forecast as fc  # noqa: E402
from core import historical as h  # noqa: E402
from core import permintaan as perm  # noqa: E402
from core import procurement as proc  # noqa: E402
from core import reference as ref  # noqa: E402
from core import shelf_life as sl  # noqa: E402
from core import simulasi as sim  # noqa: E402
from core import stats  # noqa: E402
from database import db  # noqa: E402


# ---------- Tes lama (Wajib tetap lulus - Poin 10) ----------
def test_peluang_seragam():
    assert sl.peluang_lewat(0, 1, 2, 1) == 0
    assert sl.peluang_lewat(1, 1, 2, 1) == 1
    assert abs(sl.peluang_lewat(0, 0, 10, 5) - 0.5) < 1e-12
    assert abs(sl.peluang_lewat(5, 0, 10, 2.5) - 0.5) < 1e-12
    assert sl.peluang_lewat(3, 7, 7, 3) == 0 and sl.peluang_lewat(4, 7, 7, 3) == 1


def test_referensi_parsing():
    prod, _ = ref.load_reference()
    tab = ref.build_shelf_life_table(prod)
    assert len(tab) == 3 * len(prod)
    r = tab[(tab.produk_id == 113) & (tab.lokasi == "Kulkas")].iloc[0]
    assert (r.min_hari, r.maks_hari, r.tengah_hari) == (1, 2, 1.5)
    s = tab[(tab.produk_id == 27) & (tab.lokasi == "Kulkas")].iloc[0]
    assert s.jenis == ref.JENIS_TANGGAL_KEMASAN and np.isnan(s.tengah_hari)


def test_status_dan_fifo():
    prod, _ = ref.load_reference()
    tab = ref.build_shelf_life_table(prod)
    t = date(2026, 1, 10)
    mk = lambda i, d: dict(id=i, nama="Ayam", produk_id=113, jumlah=1, satuan="kg", lokasi="Kulkas", suhu_c=4,  # noqa: E731
                           tanggal_diterima=str(t - timedelta(days=d)), tanggal_kedaluwarsa_aktual=None, catatan="")
    ev = sl.evaluasi_inventaris(pd.DataFrame([mk(1, 0), mk(2, 3)]), tab, prod, t)
    assert ev.loc[ev.id == 2, "status"].iloc[0] == "Kritis"
    assert ev.loc[ev.id == 2, "urutan_fifo"].iloc[0] == 1 and ev.iloc[0]["id"] == 2
    assert ev.loc[ev.id == 2, "urutan_fefo"].iloc[0] == 1


def test_km_numpy():
    w, S = stats.km_kurva([1, 2, 3, 4], [1, 1, 0, 1])
    assert np.allclose(S, [0.75, 0.5, 0.0])
    assert abs(stats.peluang_km([1, 2, 3, 4], [1, 1, 0, 1], 1, 1) - 1 / 3) < 1e-9
    assert np.isnan(stats.peluang_km([1, 2, 3, 4], [1, 1, 0, 1], 1, 10))


def test_praproses_tidak_mengarang():
    df = pd.DataFrame({"hari": [5, -1, None, 8], "rusak": ["ya", "tidak", "tidak", "xx"]})
    out, lap = h.praproses(df, {"durasi": "hari", "kejadian": "rusak"})
    assert len(out) == 1 and lap["baris_valid"] == 1


def test_contoh_historis_dan_normalitas():
    ch = h.buat_contoh_historis()
    assert len(ch) == 72 and set(ch["kejadian"].unique()) == {0, 1}
    prod, _ = ref.load_reference()
    tab = ref.build_shelf_life_table(prod)
    num = stats.tabel_numerik(tab, prod)
    desk = stats.deskriptif_per_lokasi(num)
    for kol in ("Q1", "Q3", "IQR", "Skewness"):
        assert kol in desk.columns
    norm = stats.uji_normalitas(num["hari"])
    assert norm is not None and norm["p"] < 0.05 and norm["skew"] > 0


# ---------- Tes Baru Bagian 9 (1 s.d. 14 + Sanity Check) ----------
def test_01_muat_permintaan_760_baris():
    df = perm.muat_permintaan(cfg.BUNDLED_PERMINTAAN)
    assert len(df) == 760
    assert df["tanggal"].iloc[0].strftime("%Y-%m-%d") == "2013-10-04"
    assert df["tanggal"].iloc[-1].strftime("%Y-%m-%d") == "2015-11-07"
    assert int(df.isna().sum().sum()) == 0


def test_02_format_tanggal_mendeley():
    s = perm.parse_tanggal_fleksibel(pd.Series(["10.4.2013", "11.7.2015"]))
    assert s.iloc[0] == pd.Timestamp(2013, 10, 4)
    assert s.iloc[1] == pd.Timestamp(2015, 11, 7)


def test_03_deskriptif_ayam_porsi():
    df = perm.muat_permintaan(cfg.BUNDLED_PERMINTAAN)
    assert abs(float(df["ayam_porsi"].mean()) - 30.40) <= 0.05
    assert abs(float(df["ayam_porsi"].std(ddof=1)) - 11.95) <= 0.05
    assert abs(float(df["daging_porsi"].mean()) - 76.21) <= 0.05
    assert abs(float(df["daging_porsi"].std(ddof=1)) - 27.23) <= 0.05


def test_04_pola_hari_ayam_sabtu_minggu():
    df = perm.muat_permintaan(cfg.BUNDLED_PERMINTAAN)
    per_hari = df.groupby("hari")["ayam_porsi"].mean()
    # Sabtu = index 5, Minggu = index 6
    assert abs(float(per_hari.loc[5]) - 46.55) <= 0.05
    assert abs(float(per_hari.loc[6]) - 21.00) <= 0.05


def test_05_konversi_kg_dan_rop_sabtu_ayam():
    df = perm.ke_kg(perm.muat_permintaan(cfg.BUNDLED_PERMINTAAN), {"ayam": 200.0})
    assert abs(float(df["ayam_kg"].mean()) - 6.08) <= 0.05
    p_hari = proc.parameter_per_hari(df, "ayam_kg")
    m_sab = float(p_hari.loc[5, "mean"])
    s_sab = float(p_hari.loc[5, "std"])
    ss_sab = proc.safety_stock(s_sab, L_hari=1.0, z=1.645)
    rop_sab = proc.reorder_point(m_sab, L_hari=1.0, ss=ss_sab)
    assert abs(rop_sab - 13.3) <= 0.06


def test_06_safety_stock_monoton():
    ss_l1 = proc.safety_stock(2.0, L_hari=1.0, z=proc.z_dari_layanan(0.90))
    ss_l2 = proc.safety_stock(2.0, L_hari=2.0, z=proc.z_dari_layanan(0.90))
    ss_sl98 = proc.safety_stock(2.0, L_hari=2.0, z=proc.z_dari_layanan(0.98))
    assert ss_l2 > ss_l1
    assert ss_sl98 > ss_l2


def test_07_kuantitas_pesan_batas():
    for stok in (0.0, 5.0, 15.0, 25.0):
        for s_target in (10.0, 20.0):
            for s_cap in (12.0, 18.0):
                q = proc.kuantitas_pesan(stok, 0.0, s_target, s_cap, moq=5.0)
                assert q >= 0.0
                assert q <= max(0.0, s_cap - stok) + 1e-9


def test_08_09_backtest_kebijakan_c_dan_seed_reproducible():
    df = perm.ke_kg(perm.muat_permintaan(cfg.BUNDLED_PERMINTAAN))
    p_hari = proc.parameter_per_hari(df, "ayam_kg")
    h1 = sim.bandingkan_kebijakan(p_hari, df_kg=df, kolom="ayam_kg", mode="backtest",
                                  masa_simpan_hari=2.0, L_rata=1.0, tingkat_layanan=0.95, seed=123)
    h2 = sim.bandingkan_kebijakan(p_hari, df_kg=df, kolom="ayam_kg", mode="backtest",
                                  masa_simpan_hari=2.0, L_rata=1.0, tingkat_layanan=0.95, seed=123)
    # Poin 9: seed sama -> hasil sama persis
    assert np.allclose(h1["% Hari Kehabisan Stok"].values, h2["% Hari Kehabisan Stok"].values)
    assert np.allclose(h1["Barang Terbuang (kg)"].values, h2["Barang Terbuang (kg)"].values)
    # Poin 8: Kebijakan C % hari kehabisan stok <= 8% pada target 95% (data in-sample)
    rc = h1[h1["Kebijakan"] == sim.KEBIJAKAN_C].iloc[0]
    assert float(rc["% Hari Kehabisan Stok"]) <= 8.0


def test_11_12_13_mode_manual_dan_label_sumber():
    # Poin 11: mean=10, cv=0.30, L=1, z=1.645 -> std=3.0, SS≈4.935 (4.94), ROP≈14.935 (14.94)
    pm = proc.parameter_manual(10.0, cv=0.30)
    std_v = float(pm.loc[0, "std"])
    ss_v = proc.safety_stock(std_v, L_hari=1.0, z=1.645)
    rop_v = proc.reorder_point(10.0, L_hari=1.0, ss=ss_v)
    assert abs(std_v - 3.0) < 1e-9
    assert abs(ss_v - 4.94) <= 0.05
    assert abs(rop_v - 14.94) <= 0.05

    # Poin 12: CV lebih besar -> SS lebih besar; mean=0 tidak error
    pm_high = proc.parameter_manual(10.0, cv=0.50)
    ss_high = proc.safety_stock(float(pm_high.loc[0, "std"]), L_hari=1.0, z=1.645)
    assert ss_high > ss_v
    pm_zero = proc.parameter_manual(0.0, cv=0.30)
    tbl_z, _ = proc.tabel_perencanaan_mingguan(pm_zero, L_hari=1.0, R_hari=1.0)
    assert (tbl_z["ROP (kg)"] == 0.0).all()

    # Poin 13: penanda sumber='asumsi' untuk manual, sumber='data' untuk data
    assert (pm["sumber"] == "asumsi").all()
    df = perm.ke_kg(perm.muat_permintaan(cfg.BUNDLED_PERMINTAAN))
    pd_data = proc.parameter_per_hari(df, "ayam_kg")
    assert (pd_data["sumber"] == "data").all()


def test_14_unggah_permintaan_pindah_mode_manual_ke_data():
    old_db = cfg.DB_PATH
    try:
        cfg.DB_PATH = Path(tempfile.mkdtemp()) / "test_mode.db"
        db.init_db()
        db.simpan_parameter_item("udang", 200, gram_per_porsi=150.0, mode_permintaan="manual", mean_manual_kg_hari=3.0)
        assert db.get_parameter_item("udang")["mode_permintaan"] == "manual"

        df_up = pd.DataFrame({
            "tanggal": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "jumlah_porsi": [20.0, 25.0, 30.0],
        })
        db.unggah_permintaan_item("udang", df_up, gram_per_porsi=150.0, produk_id=200)
        assert db.get_parameter_item("udang")["mode_permintaan"] == "data"
    finally:
        cfg.DB_PATH = old_db


def test_15_sanity_masa_simpan_lebih_pendek_dari_siklus():
    pm = proc.parameter_manual(8.0, cv=0.30)
    tbl, info = proc.tabel_perencanaan_mingguan(pm, L_hari=2.0, R_hari=1.0, masa_simpan_hari=1.5)
    assert not tbl.empty
    assert len(info["peringatan"]) >= 1
    assert any("lebih pendek dari siklus" in w for w in info["peringatan"])
