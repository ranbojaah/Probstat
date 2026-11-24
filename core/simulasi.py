"""Simulasi persediaan harian (Backtest & Monte Carlo) untuk membandingkan Kebijakan A, B, dan C dengan aturan FEFO."""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as cfg
from core import procurement as proc
from core import stats as stats_mod

KEBIJAKAN_A = "A. Naif (rata-rata harian)"
KEBIJAKAN_B = "B. ROP + Safety Stock (tanpa batas masa simpan)"
KEBIJAKAN_C = "C. ROP + Safety Stock + Batas Masa Simpan (usulan)"


def _jalankan_lintasan(
    permintaan_seri: np.ndarray,
    hari_seri: np.ndarray,
    param_hari: pd.DataFrame,
    kebijakan: str,
    masa_simpan_hari: float = 2.0,
    L_rata: float = 1.0,
    L_std: float = 0.0,
    tingkat_layanan: float = 0.95,
    Cu: float = 60000.0,
    Co: float = 40000.0,
    seed: int = 42,
) -> dict:
    """Simulasi inventaris harian dengan konsumsi FEFO untuk satu lintasan permintaan."""
    rng = np.random.default_rng(seed)
    n_hari = len(permintaan_seri)
    z = proc.z_dari_layanan(tingkat_layanan)

    means = param_hari["mean"].values.astype(float)
    stds = param_hari["std"].values.astype(float)
    rata_umum = float(means.mean())
    m_simpan = max(1, int(np.ceil(float(masa_simpan_hari))))
    L_int_base = max(1, int(round(float(L_rata))))

    # Target order-up-to per hari-dalam-minggu (untuk hari kedatangan pesanan)
    R_hari = 1.0
    S_hari = np.zeros(7, dtype=float)
    S_cap_hari = np.zeros(7, dtype=float)
    for h in range(7):
        # Urutan permintaan mulai dari hari kedatangan pesanan
        urutan = [means[(h + k) % 7] for k in range(14)]
        # Gunakan deviasi standar pada puncak siklus L+R agar cakupan hari >= target layanan
        s_siklus = max(stds[h], stds[(h + L_int_base) % 7])
        S_hari[h] = proc.order_up_to(urutan, L_rata, R_hari, s_siklus, z=z, std_L=L_std)
        # Batas masa simpan konservatif mencakup L + masa_simpan_hari sejak tanggal pesan
        S_cap_hari[h] = proc.stok_maks_masa_simpan(urutan, float(L_int_base + m_simpan))

    # Stok disimpan sebagai list batch: [jumlah_kg, sisa_umur_hari]
    # Mulai dengan stok awal sebesar kebutuhan hari pertama
    h0 = int(hari_seri[0])
    stok_awal = S_hari[h0] if kebijakan != KEBIJAKAN_A else rata_umum
    if kebijakan == KEBIJAKAN_C:
        stok_awal = min(stok_awal, S_cap_hari[h0])
    batches: list[list[float]] = [[float(stok_awal), float(m_simpan)]]
    # Pesanan dalam perjalanan: list of [hari_tiba, jumlah_kg]
    pipeline: list[list[float]] = []

    hari_stockout = 0
    total_permintaan = 0.0
    total_terpenuhi = 0.0
    total_terbuang = 0.0
    catatan_stok = np.zeros(n_hari, dtype=float)

    for t in range(n_hari):
        # 1. Pesanan yang tiba pagi hari t masuk ke gudang dengan masa simpan penuh
        tiba_baru = []
        for t_tiba, qty in pipeline:
            if t_tiba <= t:
                if qty > 0:
                    batches.append([qty, float(m_simpan)])
            else:
                tiba_baru.append([t_tiba, qty])
        pipeline = tiba_baru

        # 2. Urutkan FEFO: sisa umur terkecil dipakai lebih dulu
        batches.sort(key=lambda b: b[1])
        stok_pagi = sum(b[0] for b in batches)
        catatan_stok[t] = stok_pagi

        # 3. Permintaan hari t terjadi dan dipenuhi secara FEFO
        d_t = max(0.0, float(permintaan_seri[t]))
        total_permintaan += d_t
        sisa_butuh = d_t
        for b in batches:
            if sisa_butuh <= 0:
                break
            ambil = min(b[0], sisa_butuh)
            b[0] -= ambil
            sisa_butuh -= ambil
        terpenuhi = d_t - sisa_butuh
        total_terpenuhi += terpenuhi
        if sisa_butuh > 1e-6:
            hari_stockout += 1

        # 4. Akhir hari: umur simpan berkurang 1 hari; batch dengan sisa <= 0 dianggap busuk/terbuang
        batches_sisa = []
        for qty, sisa_u in batches:
            if qty <= 1e-9:
                continue
            sisa_baru = sisa_u - 1.0
            if sisa_baru <= 1e-9:
                total_terbuang += qty
            else:
                batches_sisa.append([qty, sisa_baru])
        batches = batches_sisa

        # 5. Keputusan pemesanan ulang untuk menutupi hari mendatang
        stok_akhir = sum(b[0] for b in batches)
        pipe_total = sum(p[1] for p in pipeline)
        h_target = int(hari_seri[(t + 1) % n_hari])

        if L_std > 0:
            L_aktual = max(1, int(round(float(rng.normal(L_rata, L_std)))))
        else:
            L_aktual = L_int_base

        if kebijakan == KEBIJAKAN_A:
            # Kebijakan A (Naif): pesan rata-rata harian tetap
            target_s = rata_umum * L_int_base
            q = max(0.0, target_s - stok_akhir - pipe_total)
        elif kebijakan == KEBIJAKAN_B:
            # Kebijakan B: ROP + Safety Stock tanpa batas masa simpan (tambah buffer 15% stok cadangan)
            target_s = S_hari[h_target] * 1.15
            q = proc.kuantitas_pesan(stok_akhir, pipe_total, target_s, None)
        else:
            # Kebijakan C: ROP + Safety Stock + Batas Masa Simpan S_cap
            q = proc.kuantitas_pesan(stok_akhir, pipe_total, S_hari[h_target], S_cap_hari[h_target])

        if q > 1e-6:
            pipeline.append([t + L_aktual, q])

    prop_stockout = hari_stockout / n_hari if n_hari > 0 else 0.0
    ci_lo, ci_hi = stats_mod.wilson(hari_stockout, n_hari) if n_hari > 0 else (0.0, 0.0)
    fill_rate = (total_terpenuhi / total_permintaan) if total_permintaan > 0 else 1.0
    kekurangan_kg = max(0.0, total_permintaan - total_terpenuhi)
    biaya_total = kekurangan_kg * float(Cu) + total_terbuang * float(Co)

    return {
        "Kebijakan": kebijakan,
        "n_hari": n_hari,
        "hari_stockout": hari_stockout,
        "% Hari Kehabisan Stok": prop_stockout * 100.0,
        "CI 95% Bawah (%)": ci_lo * 100.0,
        "CI 95% Atas (%)": ci_hi * 100.0,
        "Tingkat Layanan (%)": (1.0 - prop_stockout) * 100.0,
        "Fill Rate (%)": fill_rate * 100.0,
        "Barang Terbuang (kg)": total_terbuang,
        "Kekurangan Stok (kg)": kekurangan_kg,
        "Rata-rata Stok (kg)": float(np.mean(catatan_stok)),
        "Total Biaya Risiko (Rp)": biaya_total,
    }


def bandingkan_kebijakan(
    param_hari: pd.DataFrame,
    df_kg: pd.DataFrame | None = None,
    kolom: str | None = None,
    mode: str = "backtest",
    n_hari_simulasi: int = 1000,
    masa_simpan_hari: float = 2.0,
    L_rata: float = 1.0,
    L_std: float = 0.0,
    tingkat_layanan: float = 0.95,
    Cu: float = 60000.0,
    Co: float = 40000.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Bandingkan Kebijakan A, B, dan C pada data historis (backtest) atau simulasi Monte Carlo (>=1.000 hari)."""
    sumber_param = str(param_hari["sumber"].iloc[0]) if "sumber" in param_hari.columns else "data"
    rng = np.random.default_rng(seed)

    if mode == "backtest" and df_kg is not None and kolom in df_kg.columns and sumber_param == "data":
        d = df_kg[["hari", kolom]].dropna()
        permintaan_seri = d[kolom].values.astype(float)
        hari_seri = d["hari"].values.astype(int)
        sumber_sim = "data"
    else:
        n_sim = max(1000, int(n_hari_simulasi))
        hari_seri = np.arange(n_sim, dtype=int) % 7
        if df_kg is not None and kolom in df_kg.columns and sumber_param == "data":
            # Bootstrap per hari-dalam-minggu dari data nyata
            sampel_hari = {h: df_kg[df_kg["hari"] == h][kolom].dropna().values.astype(float) for h in range(7)}
            permintaan_seri = np.array([
                float(rng.choice(sampel_hari[h])) if len(sampel_hari[h]) else float(param_hari.loc[h, "mean"])
                for h in hari_seri
            ], dtype=float)
            sumber_sim = "data"
        else:
            # Mode manual: bangkitkan dari Normal terpotong di 0 menggunakan mean dan std per hari
            means = param_hari["mean"].values.astype(float)
            stds = param_hari["std"].values.astype(float)
            permintaan_seri = np.array([
                max(0.0, float(rng.normal(means[h], stds[h]))) for h in hari_seri
            ], dtype=float)
            sumber_sim = "asumsi"

    hasil = []
    for i, keb in enumerate((KEBIJAKAN_A, KEBIJAKAN_B, KEBIJAKAN_C)):
        res = _jalankan_lintasan(
            permintaan_seri, hari_seri, param_hari, keb,
            masa_simpan_hari=masa_simpan_hari, L_rata=L_rata, L_std=L_std,
            tingkat_layanan=tingkat_layanan, Cu=Cu, Co=Co, seed=seed + i * 17,
        )
        res["sumber"] = sumber_sim
        hasil.append(res)
    return pd.DataFrame(hasil)
