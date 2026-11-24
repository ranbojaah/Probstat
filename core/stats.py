"""Perhitungan statistik: deskriptif, perbandingan kelompok, Kaplan-Meier, Cox PH.

lifelines dan statsmodels diimpor di dalam fungsi agar modul ini ringan dan mudah diuji.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

import config as cfg
from core import reference as ref


# ---------- Deskriptif ----------
def deskriptif(x: pd.Series) -> dict:
    x = pd.to_numeric(x, errors="coerce").dropna()
    if x.empty:
        return {}
    modus = x.mode().tolist()
    q1, q3 = float(x.quantile(.25)), float(x.quantile(.75))
    skew = float(sps.skew(x, bias=False)) if len(x) > 2 else np.nan
    return dict(n=int(len(x)), rata2=float(x.mean()), median=float(x.median()), modus=modus,
                modus_jumlah=int((x == modus[0]).sum()), varians=float(x.var(ddof=1)) if len(x) > 1 else np.nan,
                sd=float(x.std(ddof=1)) if len(x) > 1 else np.nan, min=float(x.min()), maks=float(x.max()),
                q1=q1, q3=q3, iqr=float(q3 - q1), skew=skew)


def uji_normalitas(x: pd.Series) -> dict | None:
    """Uji normalitas Shapiro-Wilk dan kemencengan (skewness)."""
    x = pd.to_numeric(x, errors="coerce").dropna()
    if len(x) < 3:
        return None
    samp = x.sample(5000, random_state=42) if len(x) > 5000 else x
    stat, p = sps.shapiro(samp)
    skew = float(sps.skew(x, bias=False))
    return dict(n=int(len(x)), W=float(stat), p=float(p), skew=skew)


def tabel_numerik(tabel: pd.DataFrame, produk: pd.DataFrame, basis: str = "tengah_hari") -> pd.DataFrame:
    """Baris (produk, lokasi) yang memiliki angka masa simpan, siap dianalisis."""
    d = tabel[tabel["jenis"].isin(ref.JENIS_NUMERIK)].merge(
        produk[["produk_id", "nama", "kategori"]], on="produk_id", how="left")
    d["hari"] = d[basis]
    return d


def deskriptif_per_lokasi(num: pd.DataFrame) -> pd.DataFrame:
    baris = []
    for nama, g in [("Semua lokasi", num)] + [(k, v) for k, v in num.groupby("lokasi")]:
        s = deskriptif(g["hari"])
        if s:
            baris.append({"Lokasi": nama, "n": s["n"], "Rata-rata": s["rata2"], "Median": s["median"],
                          "Modus": ", ".join(f"{m:g}" for m in s["modus"][:3]) + (" …" if len(s["modus"]) > 3 else ""),
                          "Q1": s["q1"], "Q3": s["q3"], "IQR": s["iqr"],
                          "Varians": s["varians"], "Simpangan baku": s["sd"],
                          "Skewness": s["skew"], "Min": s["min"], "Maks": s["maks"]})
    return pd.DataFrame(baris)


def kruskal(num: pd.DataFrame, kelompok: str) -> dict | None:
    grup = [g["hari"].values for _, g in num.groupby(kelompok) if len(g) >= 3]
    if len(grup) < 2:
        return None
    h, p = sps.kruskal(*grup)
    n = sum(len(g) for g in grup)
    eps2 = (h - len(grup) + 1) / (n - len(grup))  # epsilon-squared
    return dict(H=float(h), p=float(p), k=len(grup), n=n, eps2=float(max(eps2, 0)))


def wilcoxon_berpasangan(num: pd.DataFrame, a: str, b: str) -> dict | None:
    w = num.pivot_table(index="produk_id", columns="lokasi", values="hari", aggfunc="first")
    if a not in w or b not in w:
        return None
    w = w[[a, b]].dropna()
    if len(w) < 6 or (w[a] == w[b]).all():
        return None
    stat, p = sps.wilcoxon(w[a], w[b])
    return dict(n=len(w), stat=float(stat), p=float(p), median_a=float(w[a].median()), median_b=float(w[b].median()))


def wilson(k: int, n: int) -> tuple[float, float]:
    from statsmodels.stats.proportion import proportion_confint
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return float(lo), float(hi)


def laju_per_kelompok(df: pd.DataFrame, kolom: str, flag: str) -> pd.DataFrame:
    """Proporsi flag==True per kelompok dengan CI Wilson 95%."""
    baris = []
    for k, g in df.groupby(kolom, dropna=False):
        n, x = len(g), int(g[flag].sum())
        lo, hi = wilson(x, n) if n > 0 else (np.nan, np.nan)
        baris.append({kolom: "Tidak diketahui" if pd.isna(k) else k, "n": n, "jumlah": x,
                      "proporsi": x / n, "ci_bawah": lo, "ci_atas": hi})
    return pd.DataFrame(baris).sort_values("proporsi", ascending=False)


# ---------- Kaplan-Meier ----------
def km_kurva(d, e) -> tuple[np.ndarray, np.ndarray]:
    """Estimator Kaplan-Meier (numpy) - dipakai untuk bootstrap cepat."""
    d = np.asarray(d, float)
    e = np.asarray(e, int)
    de = np.sort(d[e == 1])
    ut = np.unique(de)
    if ut.size == 0:
        return ut, ut
    ds = np.sort(d)
    berisiko = len(ds) - np.searchsorted(ds, ut, side="left")
    kej = np.searchsorted(de, ut, side="right") - np.searchsorted(de, ut, side="left")
    return ut, np.cumprod(1 - kej / berisiko)


def km_s(waktu: np.ndarray, S: np.ndarray, t: float) -> float:
    i = np.searchsorted(waktu, t, side="right") - 1
    return 1.0 if i < 0 else float(S[i])


def peluang_km(d, e, umur: float, horizon: float) -> float:
    """P(umur < T <= umur+h | T > umur). NaN bila di luar rentang pengamatan."""
    d = np.asarray(d, float)
    if umur + horizon > d.max():
        return np.nan
    w, S = km_kurva(d, e)
    sa = km_s(w, S, umur)
    if sa <= 0:
        return np.nan
    return 1.0 - km_s(w, S, umur + horizon) / sa


def peluang_km_ci(d, e, umur: float, horizons=cfg.HORIZON_HARI, B: int = cfg.BOOTSTRAP_ULANG) -> pd.DataFrame:
    d = np.asarray(d, float)
    e = np.asarray(e, int)
    rng = np.random.default_rng(cfg.BOOTSTRAP_SEED)
    n = len(d)
    idx = rng.integers(0, n, size=(B, n))
    baris = []
    for h in horizons:
        p = peluang_km(d, e, umur, h)
        boot = np.array([peluang_km(d[i], e[i], umur, h) for i in idx])
        valid = boot[~np.isnan(boot)]
        ok = not np.isnan(p) and len(valid) >= 0.8 * B
        baris.append(dict(horizon=h, p=p, ci_bawah=np.percentile(valid, 2.5) if ok else np.nan,
                          ci_atas=np.percentile(valid, 97.5) if ok else np.nan))
    return pd.DataFrame(baris)


def pilih_kelompok_km(hist: pd.DataFrame, lokasi: str) -> tuple[pd.DataFrame | None, str]:
    """Kelompok data historis yang cukup untuk prediksi. Mengembalikan (data, keterangan)."""
    g = hist[hist["lokasi"] == lokasi]
    if len(g) and g["kejadian"].sum() >= cfg.MIN_KEJADIAN_KM:
        return g, f"data historis untuk lokasi {lokasi}"
    if hist["kejadian"].sum() >= cfg.MIN_KEJADIAN_KM:
        return hist, "seluruh data historis (tidak dipisah per lokasi karena kejadian pada lokasi ini terlalu sedikit)"
    return None, ""


def km_fit(d, e, label: str = ""):
    from lifelines import KaplanMeierFitter
    return KaplanMeierFitter().fit(d, event_observed=e, label=label)


def logrank(hist: pd.DataFrame, kolom: str) -> dict | None:
    from lifelines.statistics import multivariate_logrank_test
    g = hist.dropna(subset=[kolom])
    ok = [k for k, v in g.groupby(kolom) if len(v) >= 5 and v["kejadian"].sum() >= 1]
    g = g[g[kolom].isin(ok)]
    if len(ok) < 2:
        return None
    r = multivariate_logrank_test(g["durasi_hari"], g[kolom], g["kejadian"])
    return dict(stat=float(r.test_statistic), p=float(r.p_value), k=len(ok))


# ---------- Cox ----------
def siapkan_cox(hist: pd.DataFrame, pakai_suhu: bool, pakai_lokasi: bool, pakai_kategori: bool):
    X = hist[["durasi_hari", "kejadian"]].copy()
    if pakai_suhu:
        X["suhu_c"] = hist["suhu_c"]
    kat = []
    if pakai_lokasi:
        kat.append("lokasi")
    if pakai_kategori:
        kat.append("kategori")
    for k in kat:
        X[k] = hist[k]
    X = X.dropna()
    if kat:
        X = pd.get_dummies(X, columns=kat, drop_first=True, dtype=float)
    X = X.loc[:, (X.nunique() > 1) | X.columns.isin(["durasi_hari", "kejadian"])]
    return X


def cox_fit(hist: pd.DataFrame, pakai_suhu=True, pakai_lokasi=True, pakai_kategori=False) -> dict:
    from lifelines import CoxPHFitter
    X = siapkan_cox(hist, pakai_suhu, pakai_lokasi, pakai_kategori)
    p = X.shape[1] - 2
    ev = int(X["kejadian"].sum())
    if p < 1:
        return dict(galat="Tidak ada kovariat dengan variasi nilai yang cukup.")
    if ev < cfg.KEJADIAN_PER_KOVARIAT * p:
        return dict(galat=f"Kejadian ({ev}) kurang dari {cfg.KEJADIAN_PER_KOVARIAT} per parameter "
                          f"({cfg.KEJADIAN_PER_KOVARIAT * p} dibutuhkan untuk {p} parameter). "
                          "Model Cox tidak dijustifikasi secara statistik.")
    penal = 0.0
    try:
        cph = CoxPHFitter(penalizer=0.0).fit(X, "durasi_hari", "kejadian")
    except Exception:  # noqa: BLE001  (mis. ConvergenceError / kolinearitas)
        penal = 0.1
        try:
            cph = CoxPHFitter(penalizer=penal).fit(X, "durasi_hari", "kejadian")
        except Exception as e:  # noqa: BLE001
            return dict(galat=f"Model Cox gagal konvergen: {e}")
    s = cph.summary[["exp(coef)", "exp(coef) lower 95%", "exp(coef) upper 95%", "p"]].reset_index()
    s.columns = ["Variabel", "Rasio hazard", "CI 95% bawah", "CI 95% atas", "Nilai p"]
    ph = None
    try:
        from lifelines.statistics import proportional_hazard_test
        t = proportional_hazard_test(cph, X, time_transform="rank").summary
        ph = pd.DataFrame({"Variabel": [str(i) for i in t.index],
                           "Statistik uji": t["test_statistic"].to_numpy(),
                           "Nilai p": t["p"].to_numpy()})
    except Exception:  # noqa: BLE001
        pass
    return dict(ringkasan=s, n=len(X), kejadian=ev, penalizer=penal, concordance=float(cph.concordance_index_), ph=ph)
