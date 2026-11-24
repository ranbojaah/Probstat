"""Peramalan permintaan harian: Naif Musiman (4 minggu), Rata-rata Hari × Indeks Bulan, dan Holt-Winters."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as cfg
from core import permintaan as perm_mod
from core import procurement as proc

METODE_NAIF = "Naif musiman (4 minggu)"
METODE_INDEKS = "Rata-rata hari × indeks bulan"
METODE_HW = "Holt-Winters (musiman 7 hari)"
DAFTAR_METODE = [METODE_NAIF, METODE_INDEKS, METODE_HW]


def metrik_evaluasi(aktual: np.ndarray, prediksi: np.ndarray) -> dict[str, float]:
    """Hitung MAE, RMSE, dan sMAPE (aman untuk nilai aktual = 0)."""
    y = np.asarray(aktual, dtype=float)
    yh = np.asarray(prediksi, dtype=float)
    err = y - yh
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    penyebut = np.abs(y) + np.abs(yh)
    smape = float(np.mean(np.where(penyebut > 1e-9, 200.0 * np.abs(err) / penyebut, 0.0)))
    return {"MAE": mae, "RMSE": rmse, "sMAPE (%)": smape}


def _pred_naif_musiman(train: pd.DataFrame, kolom: str, tgl_target: pd.Series) -> np.ndarray:
    """Rata-rata hari-dalam-minggu yang sama pada 4 pengamatan terakhir."""
    rata_4 = {}
    rata_all = float(train[kolom].mean()) if len(train) else 0.0
    for h in range(7):
        sub = train[train["hari"] == h][kolom].tail(4)
        rata_4[h] = float(sub.mean()) if len(sub) else rata_all
    return np.array([rata_4[int(t.dayofweek)] for t in pd.to_datetime(tgl_target)], dtype=float)


def _pred_hari_kali_indeks(train: pd.DataFrame, kolom: str, tgl_target: pd.Series) -> np.ndarray:
    """Rata-rata hari-dalam-minggu dikali indeks musiman bulanan."""
    rata_all = float(train[kolom].mean()) if len(train) else 0.0
    rata_hari = train.groupby("hari")[kolom].mean().to_dict()
    tbl_idx, _ = perm_mod.indeks_musiman_bulanan(train, kolom)
    peta_idx = dict(zip(tbl_idx["bulan"], tbl_idx["Indeks Musiman"]))
    out = []
    for t in pd.to_datetime(tgl_target):
        mh = float(rata_hari.get(int(t.dayofweek), rata_all))
        im = float(peta_idx.get(int(t.month), 1.0))
        out.append(max(0.0, mh * im))
    return np.array(out, dtype=float)


def _pred_holt_winters(train: pd.DataFrame, kolom: str, langkah: int) -> np.ndarray:
    """ExponentialSmoothing(seasonal_periods=7, trend=None) dengan fallback naif musiman jika gagal konvergen."""
    y = train[kolom].values.astype(float)
    if len(y) < 14:
        return np.repeat(float(np.mean(y)) if len(y) else 0.0, langkah)
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(y, trend=None, seasonal="add", seasonal_periods=7,
                                     initialization_method="estimated")
        fit = model.fit(optimized=True)
        pred = np.asarray(fit.forecast(langkah), dtype=float)
        return np.maximum(0.0, pred)
    except Exception:  # noqa: BLE001
        tgl_f = pd.date_range(pd.to_datetime(train["tanggal"].iloc[-1]) + pd.Timedelta(days=1), periods=langkah, freq="D")
        return _pred_naif_musiman(train, kolom, pd.Series(tgl_f))


def evaluasi_rolling_origin(df: pd.DataFrame, kolom: str, n_uji: int = 42) -> tuple[pd.DataFrame, str, dict]:
    """Evaluasi 3 metode peramalan dengan rolling-origin 1-langkah-ke-depan pada n_uji hari terakhir."""
    d = df[["tanggal", "hari", "bulan", kolom]].dropna().sort_values("tanggal").reset_index(drop=True)
    n_total = len(d)
    n_eval = min(int(n_uji), max(14, n_total // 5))
    mulai_uji = n_total - n_eval

    aktual = d[kolom].iloc[mulai_uji:].values.astype(float)
    pred_map = {m: np.zeros(n_eval, dtype=float) for m in DAFTAR_METODE}

    # Hitung parameter indeks sekali pada data latih awal dan update bertahap untuk kecepatan
    for i in range(n_eval):
        idx = mulai_uji + i
        train = d.iloc[:idx]
        tgl_t = pd.Series([d["tanggal"].iloc[idx]])
        pred_map[METODE_NAIF][i] = _pred_naif_musiman(train, kolom, tgl_t)[0]
        pred_map[METODE_INDEKS][i] = _pred_hari_kali_indeks(train, kolom, tgl_t)[0]

    # Untuk Holt-Winters, evaluasi rolling dalam blok 7 hari agar responsif di UI
    blok = 7
    for i in range(0, n_eval, blok):
        idx = mulai_uji + i
        langkah = min(blok, n_eval - i)
        train = d.iloc[:idx]
        pred_map[METODE_HW][i:i + langkah] = _pred_holt_winters(train, kolom, langkah)

    baris = []
    residual_map = {}
    for m in DAFTAR_METODE:
        met = metrik_evaluasi(aktual, pred_map[m])
        res = aktual - pred_map[m]
        residual_map[m] = res
        baris.append({
            "Metode": m,
            "MAE": met["MAE"],
            "RMSE": met["RMSE"],
            "sMAPE (%)": met["sMAPE (%)"],
            "q05_res": float(np.quantile(res, 0.05)),
            "q95_res": float(np.quantile(res, 0.95)),
        })

    tbl = pd.DataFrame(baris).sort_values("RMSE").reset_index(drop=True)
    terbaik = str(tbl.iloc[0]["Metode"])
    return tbl, terbaik, {"aktual": aktual, "prediksi": pred_map, "residual": residual_map,
                          "tanggal_uji": d["tanggal"].iloc[mulai_uji:].values}


def _terapkan_faktor_event(df_fc: pd.DataFrame, faktor_event_df: pd.DataFrame | None) -> pd.DataFrame:
    out = df_fc.copy()
    out["faktor_event"] = 1.0
    out["keterangan_event"] = ""
    if faktor_event_df is not None and not faktor_event_df.empty:
        tgl_s = pd.to_datetime(out["tanggal"]).dt.strftime("%Y-%m-%d")
        for _, ev in faktor_event_df.iterrows():
            m = (tgl_s >= str(ev["tanggal_mulai"])) & (tgl_s <= str(ev["tanggal_selesai"]))
            if m.any():
                f = float(ev["faktor"])
                out.loc[m, "faktor_event"] *= f
                ket = str(ev.get("keterangan", "Event"))
                out.loc[m, "keterangan_event"] = np.where(
                    out.loc[m, "keterangan_event"] == "",
                    f"{ket} (×{f:g})",
                    out.loc[m, "keterangan_event"] + f", {ket} (×{f:g})",
                )
    out["forecast_akhir"] = np.maximum(0.0, out["forecast_dasar"] * out["faktor_event"])
    out["batas_bawah"] = np.maximum(0.0, out["batas_bawah_dasar"] * out["faktor_event"])
    out["batas_atas"] = np.maximum(0.0, out["batas_atas_dasar"] * out["faktor_event"])
    out["dipengaruhi_event"] = out["faktor_event"] != 1.0
    return out


def ramal_horizon(
    df: pd.DataFrame,
    kolom: str,
    metode: str = METODE_INDEKS,
    horizon: int = 14,
    faktor_event_df: pd.DataFrame | None = None,
    mulai_tanggal: date | str | None = None,
    residual_kuantil: tuple[float, float] | None = None,
) -> pd.DataFrame:
    """Ramal permintaan harian untuk horizon hari ke depan pada bahan mode Data."""
    d = df[["tanggal", "hari", "bulan", kolom]].dropna().sort_values("tanggal").reset_index(drop=True)
    if mulai_tanggal is None:
        t0 = pd.to_datetime(d["tanggal"].iloc[-1]) + pd.Timedelta(days=1)
    else:
        t0 = pd.to_datetime(mulai_tanggal)
    tgl_target = pd.Series(pd.date_range(t0, periods=int(horizon), freq="D"))

    if metode == METODE_NAIF:
        pred = _pred_naif_musiman(d, kolom, tgl_target)
    elif metode == METODE_HW:
        pred = _pred_holt_winters(d, kolom, int(horizon))
    else:
        pred = _pred_hari_kali_indeks(d, kolom, tgl_target)

    if residual_kuantil is not None:
        q_lo, q_hi = float(residual_kuantil[0]), float(residual_kuantil[1])
    else:
        std_h = d.groupby("hari")[kolom].std(ddof=1).to_dict()
        q_lo, q_hi = -1.645 * float(np.nanmean(list(std_h.values()))), 1.645 * float(np.nanmean(list(std_h.values())))

    fc = pd.DataFrame({
        "tanggal": tgl_target,
        "hari": tgl_target.dt.dayofweek,
        "Hari": tgl_target.dt.dayofweek.map(lambda i: cfg.HARI_ID[int(i)]),
        "forecast_dasar": pred,
        "batas_bawah_dasar": np.maximum(0.0, pred + q_lo),
        "batas_atas_dasar": np.maximum(0.0, pred + q_hi),
        "metode": metode,
        "sumber": "data",
    })
    return _terapkan_faktor_event(fc, faktor_event_df)


def ramal_manual(
    mean_kg_hari: float,
    cv: float = cfg.CV_DEFAULT_MANUAL,
    horizon: int = 14,
    profil_hari: list[float] | np.ndarray | None = None,
    faktor_event_df: pd.DataFrame | None = None,
    mulai_tanggal: date | str | None = None,
    z: float = 1.645,
) -> pd.DataFrame:
    """Ramalan datar (atau dengan profil hari pinjaman) untuk bahan mode Manual — selalu dilabeli sumber='asumsi'."""
    t0 = pd.to_datetime(mulai_tanggal or (date.today() + timedelta(days=1)))
    tgl_target = pd.Series(pd.date_range(t0, periods=int(horizon), freq="D"))
    param = proc.parameter_manual(mean_kg_hari, cv=cv, profil_hari=profil_hari)
    peta_m = param["mean"].to_dict()
    peta_s = param["std"].to_dict()

    hari_idx = tgl_target.dt.dayofweek
    pred = np.array([float(peta_m[int(h)]) for h in hari_idx], dtype=float)
    stds = np.array([float(peta_s[int(h)]) for h in hari_idx], dtype=float)

    fc = pd.DataFrame({
        "tanggal": tgl_target,
        "hari": hari_idx,
        "Hari": hari_idx.map(lambda i: cfg.HARI_ID[int(i)]),
        "forecast_dasar": pred,
        "batas_bawah_dasar": np.maximum(0.0, pred - float(z) * stds),
        "batas_atas_dasar": np.maximum(0.0, pred + float(z) * stds),
        "metode": "Rata-rata manual (asumsi pengguna)",
        "sumber": "asumsi",
    })
    return _terapkan_faktor_event(fc, faktor_event_df)
