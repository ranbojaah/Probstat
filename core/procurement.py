"""Inti perencanaan pengadaan bahan baku perishable: parameter per hari, safety stock, ROP, batas masa simpan, dan Newsvendor."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

import config as cfg


def z_dari_layanan(tingkat_layanan: float) -> float:
    """Konversi tingkat layanan (0..1) ke skor-z baku normal. Untuk 0,95 dikembalikan 1,645 sesuai acuan spesifikasi."""
    p = float(np.clip(tingkat_layanan, 0.50, 0.9999))
    if abs(p - 0.95) < 1e-6:
        return 1.645
    return float(sps.norm.ppf(p))


def parameter_per_hari(df_kg: pd.DataFrame, kolom: str) -> pd.DataFrame:
    """Hitung parameter permintaan per hari dalam minggu (index 0=Senin .. 6=Minggu) dari data historis."""
    if kolom not in df_kg.columns:
        raise ValueError(f"Kolom '{kolom}' tidak ditemukan pada DataFrame permintaan.")
    d = df_kg[["hari", kolom]].dropna().copy()
    baris = []
    for h in range(7):
        s = pd.to_numeric(d[d["hari"] == h][kolom], errors="coerce").dropna()
        n = int(len(s))
        mean_v = float(s.mean()) if n > 0 else 0.0
        std_v = float(s.std(ddof=1)) if n > 1 else 0.0
        q95_v = float(s.quantile(0.95)) if n > 0 else 0.0
        baris.append({
            "hari": h,
            "nama_hari": cfg.HARI_ID[h],
            "mean": mean_v,
            "std": std_v,
            "cv": (std_v / mean_v) if mean_v > 0 else 0.0,
            "q95_empiris": q95_v,
            "n": n,
            "sumber": "data",
        })
    return pd.DataFrame(baris).set_index("hari", drop=False)


def parameter_manual(mean_kg_hari: float, cv: float = cfg.CV_DEFAULT_MANUAL,
                     profil_hari: list[float] | np.ndarray | None = None) -> pd.DataFrame:
    """Bentuk tabel parameter per hari (index 0..6) untuk bahan mode manual (berbasis asumsi pengguna)."""
    mean_base = max(0.0, float(mean_kg_hari or 0.0))
    cv_val = max(0.0, float(cv or 0.0))
    if profil_hari is not None and len(profil_hari) == 7:
        rasio = np.asarray(profil_hari, dtype=float)
        rata_r = float(rasio.mean())
        rasio = (rasio / rata_r) if rata_r > 0 else np.ones(7)
    else:
        rasio = np.ones(7, dtype=float)

    baris = []
    for h in range(7):
        m_h = mean_base * float(rasio[h])
        s_h = cv_val * m_h
        baris.append({
            "hari": h,
            "nama_hari": cfg.HARI_ID[h],
            "mean": m_h,
            "std": s_h,
            "cv": cv_val,
            "q95_empiris": m_h + 1.645 * s_h,
            "n": 0,
            "sumber": "asumsi",
        })
    return pd.DataFrame(baris).set_index("hari", drop=False)


def safety_stock(std, L_hari: float, z: float = 1.645, std_L: float = 0.0, mean_d=0.0):
    """Hitung safety stock berbasis pendekatan Normal (mendukung lead time konstan maupun bervariasi)."""
    L = np.maximum(0.0, np.asarray(L_hari, dtype=float))
    s_d = np.maximum(0.0, np.asarray(std, dtype=float))
    s_L = np.maximum(0.0, np.asarray(std_L, dtype=float))
    m_d = np.maximum(0.0, np.asarray(mean_d, dtype=float))
    ss = float(z) * np.sqrt(L * (s_d ** 2) + (m_d ** 2) * (s_L ** 2))
    return float(ss) if np.ndim(std) == 0 and np.ndim(mean_d) == 0 else ss


def rasio_residual_harian(df_kg: pd.DataFrame, kolom: str) -> pd.Series:
    """Hitung rasio permintaan harian terhadap rata-rata hari-dalam-minggu: r_t = d_t / mean_hari(t)."""
    d = df_kg[["hari", kolom]].dropna().copy()
    rata_h = d.groupby("hari")[kolom].transform("mean")
    rasio = np.where(rata_h > 0, d[kolom] / rata_h, 1.0)
    return pd.Series(rasio, index=d.index, name="rasio_residual")


def safety_stock_empiris(residual_rasio, mean_d, L_hari: float, tingkat_layanan: float = 0.95):
    """Safety stock non-parametrik berbasis kuantil empiris dari rasio permintaan/rata-rata-hari."""
    r = pd.Series(residual_rasio).dropna().values.astype(float)
    if r.size == 0:
        return safety_stock(0.0, L_hari)
    p = float(np.clip(tingkat_layanan, 0.50, 0.9999))
    q = float(np.quantile(r, p))
    # Jika r berupa rasio d / mean_h (rata-rata ~ 1), selisihnya adalah (q - 1); jika sudah terpusat di 0, pakai q.
    faktor_lebih = max(0.0, (q - 1.0) if float(np.mean(r)) > 0.5 else q)
    L = max(0.0, float(L_hari))
    m_d = np.maximum(0.0, np.asarray(mean_d, dtype=float))
    ss_emp = faktor_lebih * m_d * np.sqrt(L)
    return float(ss_emp) if np.ndim(mean_d) == 0 else ss_emp


def reorder_point(mean_d, L_hari: float, ss):
    """ROP = mean_d * L + SS."""
    L = max(0.0, float(L_hari))
    rop = np.maximum(0.0, np.asarray(mean_d, dtype=float)) * L + np.maximum(0.0, np.asarray(ss, dtype=float))
    return float(rop) if np.ndim(mean_d) == 0 and np.ndim(ss) == 0 else rop


def _jumlah_forecast_durasi(forecast_harian, durasi_hari: float) -> float:
    dur = max(0.0, float(durasi_hari))
    if dur == 0.0:
        return 0.0
    if np.ndim(forecast_harian) == 0 or isinstance(forecast_harian, (int, float, np.number)):
        return max(0.0, float(forecast_harian)) * dur
    arr = np.maximum(0.0, np.asarray(list(forecast_harian), dtype=float))
    if arr.size == 0:
        return 0.0
    penuh = int(np.floor(dur))
    sisa = dur - penuh
    idx_penuh = [i % arr.size for i in range(penuh)]
    total = float(arr[idx_penuh].sum()) if penuh > 0 else 0.0
    if sisa > 0:
        total += sisa * float(arr[penuh % arr.size])
    return total


def order_up_to(forecast_hari_ke_depan, L_hari: float, R_hari: float, std: float,
                z: float = 1.645, std_L: float = 0.0) -> float:
    """Target stok periodic review: S = sum(forecast selama L+R hari) + SS(L+R)."""
    lr = max(0.0, float(L_hari) + float(R_hari))
    permintaan_lr = _jumlah_forecast_durasi(forecast_hari_ke_depan, lr)
    rata_lr = (permintaan_lr / lr) if lr > 0 else 0.0
    ss_lr = safety_stock(float(std), lr, z=z, std_L=std_L, mean_d=rata_lr)
    return float(permintaan_lr + ss_lr)


def stok_maks_masa_simpan(forecast_harian, masa_simpan_hari: float) -> float:
    """Batas stok tertinggi agar tidak busuk: jumlah forecast selama masa_simpan_hari ke depan."""
    return _jumlah_forecast_durasi(forecast_harian, masa_simpan_hari)


def kuantitas_pesan(stok_sekarang: float, pesanan_dalam_perjalanan: float,
                    S: float, S_cap: float | None = None, moq: float = 0.0) -> float:
    """Hitung jumlah pesan q = max(0, min(S, S_cap) - stok - pipeline), tidak pernah negatif atau melebihi S_cap - stok."""
    stok = max(0.0, float(stok_sekarang))
    pipe = max(0.0, float(pesanan_dalam_perjalanan))
    target = float(S) if (S_cap is None or pd.isna(S_cap)) else min(float(S), float(S_cap))
    batas_atas = (float(S_cap) - stok - pipe) if (S_cap is not None and not pd.isna(S_cap)) else (float(S) - stok - pipe)
    batas_atas = max(0.0, batas_atas)
    q_mentah = max(0.0, target - stok - pipe)
    if q_mentah <= 0.0:
        return 0.0
    moq_val = max(0.0, float(moq or 0.0))
    if moq_val > 0 and q_mentah < moq_val:
        q_mentah = min(moq_val, batas_atas)
    return float(min(q_mentah, batas_atas))


def layanan_efektif_dari_cap(S_cap: float, permintaan_lr: float, std_lr: float) -> float:
    """Estimasi tingkat layanan efektif (%) jika stok dibatasi oleh S_cap < S."""
    if std_lr <= 1e-9:
        return 1.0 if S_cap >= permintaan_lr else 0.5
    z_eff = (float(S_cap) - float(permintaan_lr)) / float(std_lr)
    return float(np.clip(sps.norm.cdf(z_eff), 0.01, 0.9999))


def newsvendor(forecast_mean: float, forecast_std: float, Cu: float, Co: float) -> dict:
    """Model Newsvendor satu periode untuk bahan mudah rusak: CR = Cu/(Cu+Co), Q* = mean + z(CR)*std."""
    cu = max(0.0, float(Cu))
    co = max(0.0, float(Co))
    if cu + co <= 0:
        cr = 0.5
    else:
        cr = float(np.clip(cu / (cu + co), 1e-4, 1.0 - 1e-4))
    z_cr = float(sps.norm.ppf(cr))
    q_star = max(0.0, float(forecast_mean) + z_cr * max(0.0, float(forecast_std)))
    return {"CR": cr, "z_CR": z_cr, "Q_star": q_star, "Cu": cu, "Co": co}


def tabel_perencanaan_mingguan(
    param_hari: pd.DataFrame,
    L_hari: float = 1.0,
    R_hari: float = 1.0,
    tingkat_layanan: float = 0.95,
    masa_simpan_hari: float | None = 2.0,
    std_L: float = 0.0,
    residual_rasio: pd.Series | None = None,
    stok_sekarang: float = 0.0,
    pipeline_kg: float = 0.0,
    moq_kg: float = 0.0,
    indeks_bulan: float = 1.0,
    faktor_event: float = 1.0,
) -> tuple[pd.DataFrame, dict]:
    """Susun tabel pengadaan lengkap per hari-dalam-minggu (Senin..Minggu) beserta peringatan batas masa simpan."""
    z = z_dari_layanan(tingkat_layanan)
    pengali = max(0.0, float(indeks_bulan) * float(faktor_event))
    means = param_hari["mean"].values.astype(float) * pengali
    stds = param_hari["std"].values.astype(float) * pengali
    sumber = str(param_hari["sumber"].iloc[0]) if "sumber" in param_hari.columns else "data"

    lr = max(0.0, float(L_hari) + float(R_hari))
    m_simpan = float(masa_simpan_hari) if (masa_simpan_hari is not None and not pd.isna(masa_simpan_hari)) else None

    baris = []
    n_terbatas = 0
    layanan_eff_min = float(tingkat_layanan)

    for h in range(7):
        m_h = float(means[h])
        s_h = float(stds[h])
        ss_norm = safety_stock(s_h, L_hari, z=z, std_L=std_L, mean_d=m_h)
        if residual_rasio is not None and len(residual_rasio) > 0:
            ss_emp = safety_stock_empiris(residual_rasio, m_h, L_hari, tingkat_layanan=tingkat_layanan)
        else:
            ss_emp = ss_norm
        rop_h = reorder_point(m_h, L_hari, ss_norm)

        # Urutan forecast mulai dari hari h ke depan
        urutan_fc = [means[(h + k) % 7] for k in range(14)]
        S_h = order_up_to(urutan_fc, L_hari, R_hari, s_h, z=z, std_L=std_L)
        if m_simpan is not None and m_simpan > 0:
            S_cap_h = stok_maks_masa_simpan(urutan_fc, m_simpan)
        else:
            S_cap_h = np.nan

        q_h = kuantitas_pesan(stok_sekarang, pipeline_kg, S_h, None if np.isnan(S_cap_h) else S_cap_h, moq=moq_kg)

        perm_lr = _jumlah_forecast_durasi(urutan_fc, lr)
        std_lr = float(np.sqrt(lr * (s_h ** 2) + ((perm_lr / lr if lr > 0 else m_h) ** 2) * (std_L ** 2)))
        if not np.isnan(S_cap_h) and S_h > S_cap_h + 1e-6:
            n_terbatas += 1
            eff = layanan_efektif_dari_cap(S_cap_h, perm_lr, std_lr)
            layanan_eff_min = min(layanan_eff_min, eff)
            status_cap = f"Terbatas masa simpan (layanan efektif ≈ {eff * 100:.1f}%)"
        else:
            eff = float(tingkat_layanan)
            status_cap = "Target layanan tercapai"

        baris.append({
            "hari": h,
            "Hari": cfg.HARI_ID[h],
            "Mean (kg)": m_h,
            "Std (kg)": s_h,
            "SS Normal (kg)": ss_norm,
            "SS Empiris (kg)": ss_emp,
            "ROP (kg)": rop_h,
            "Target Stok S (kg)": S_h,
            "Stok Maks S_cap (kg)": S_cap_h,
            "Jumlah Pesan q (kg)": q_h,
            "Layanan Efektif": eff,
            "Catatan": status_cap,
            "sumber": sumber,
        })

    peringatan = []
    if m_simpan is not None and m_simpan < lr:
        peringatan.append(
            f"Masa simpan konservatif ({m_simpan:g} hari) lebih pendek dari siklus pengadaan L+R ({lr:g} hari). "
            "Bahan berisiko kedaluwarsa sebelum siklus pesan berikutnya tiba. Kurangi L+R (pesan harian) atau gunakan penyimpanan Freezer."
        )
    if n_terbatas > 0:
        peringatan.append(
            f"Pada {n_terbatas} hari dalam seminggu, target stok S melebihi batas masa simpan S_cap: "
            f"target layanan {tingkat_layanan * 100:.1f}% tidak tercapai tanpa risiko busuk (tingkat layanan efektif terendah ≈ {layanan_eff_min * 100:.1f}%). "
            "Solusi: pesan lebih sering (kurangi L+R), simpan cadangan lonjakan di Freezer, atau terima tingkat layanan lebih rendah."
        )

    info = {
        "z": z,
        "L_hari": float(L_hari),
        "R_hari": float(R_hari),
        "masa_simpan_hari": m_simpan,
        "n_hari_terbatas": n_terbatas,
        "layanan_efektif_min": layanan_eff_min,
        "peringatan": peringatan,
        "sumber": sumber,
    }
    return pd.DataFrame(baris), info
