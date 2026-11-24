"""Estimasi masa simpan, status inventaris, probabilitas, prioritas FEFO/FIFO, dan estimasi barang terbuang (expected waste)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

import config as cfg
from core import reference as ref


def cdf_seragam(t: float, mn: float, mx: float) -> float:
    if mx <= mn:
        return 1.0 if t >= mx else 0.0
    return float(np.clip((t - mn) / (mx - mn), 0.0, 1.0))


def peluang_lewat(umur: float, mn: float, mx: float, horizon: float) -> float:
    fa = cdf_seragam(umur, mn, mx)
    if fa >= 1.0:
        return 1.0
    fh = cdf_seragam(umur + horizon, mn, mx)
    return float((fh - fa) / (1.0 - fa))


def kurva_bertahan(mn: float, mx: float, t_maks: float, n: int = 200) -> tuple[np.ndarray, np.ndarray]:
    t = np.linspace(0, t_maks, n)
    return t, np.array([1 - cdf_seragam(x, mn, mx) for x in t])


def _tgl(d: pd.Timestamp, hari: float):
    return (d + pd.Timedelta(days=int(hari))).date()


def masa_simpan_produk(tabel: pd.DataFrame, produk_id: int | None, lokasi: str = "Kulkas") -> dict:
    """Ambil parameter masa simpan (min_hari, tengah_hari, maks_hari, rentang_teks, jenis) untuk (produk_id, lokasi)."""
    if produk_id is None or pd.isna(produk_id):
        return {"min_hari": np.nan, "tengah_hari": np.nan, "maks_hari": np.nan, "rentang_teks": "—", "jenis": ref.JENIS_TIDAK_ADA}
    sub = tabel[(tabel["produk_id"] == int(produk_id)) & (tabel["lokasi"] == lokasi)]
    if sub.empty:
        return {"min_hari": np.nan, "tengah_hari": np.nan, "maks_hari": np.nan, "rentang_teks": "—", "jenis": ref.JENIS_TIDAK_ADA}
    r = sub.iloc[0]
    return {
        "min_hari": float(r["min_hari"]) if pd.notna(r["min_hari"]) else np.nan,
        "tengah_hari": float(r["tengah_hari"]) if pd.notna(r["tengah_hari"]) else np.nan,
        "maks_hari": float(r["maks_hari"]) if pd.notna(r["maks_hari"]) else np.nan,
        "rentang_teks": str(r["rentang_teks"]),
        "jenis": str(r["jenis"]),
    }


def _evaluasi_baris(r: pd.Series, today: date) -> dict:
    umur = max((today - r["tanggal_diterima"].date()).days, 0)
    out = dict(umur_hari=umur, status=cfg.BELUM, catatan_estimasi="", sisa_hari=np.nan,
               tanggal_estimasi=None, tanggal_efektif=None, sisa_efektif=np.nan,
               **{f"p{h}": np.nan for h in cfg.HORIZON_HARI})
    jenis = r.get("jenis", ref.JENIS_TIDAK_ADA)
    if pd.isna(jenis):
        jenis = ref.JENIS_TIDAK_ADA
    sev_est = None  # 0 aman, 1 segera, 2 kritis

    if jenis in ref.JENIS_NUMERIK:
        mn, mx, mid = r["min_hari"], r["maks_hari"], r["tengah_hari"]
        batas = int(np.ceil(mid))
        sisa = batas - umur
        out["sisa_hari"] = sisa
        out["tanggal_estimasi"] = _tgl(r["tanggal_diterima"], batas)
        for h in cfg.HORIZON_HARI:
            out[f"p{h}"] = peluang_lewat(umur, mn, mx, h)
        if sisa <= 0:
            sev_est = 2
        elif (umur >= int(np.ceil(mn)) or sisa <= max(1.0, cfg.SEGERA_FRAKSI * mid)
              or out[f"p{cfg.RISIKO_TINGGI_HORIZON}"] >= cfg.RISIKO_TINGGI_AMBANG):
            sev_est = 1
        else:
            sev_est = 0
    elif jenis == ref.JENIS_TANPA_BATAS:
        sev_est = 0
        out["catatan_estimasi"] = ref.CATATAN_JENIS[jenis]
    else:
        out["catatan_estimasi"] = ref.CATATAN_JENIS.get(jenis, "")

    sev_akt = None
    akt = r.get("tanggal_kedaluwarsa_aktual")
    if pd.notna(akt):
        sisa_a = (akt.date() - today).days
        sev_akt = 2 if sisa_a <= 0 else (1 if sisa_a <= cfg.SEGERA_HARI_AKTUAL else 0)
        out["tanggal_efektif"] = akt.date()
        out["sisa_efektif"] = sisa_a

    if out["tanggal_estimasi"] is not None:
        if out["tanggal_efektif"] is None or out["tanggal_estimasi"] < out["tanggal_efektif"]:
            out["tanggal_efektif"] = out["tanggal_estimasi"]
            out["sisa_efektif"] = out["sisa_hari"]

    sevs = [s for s in (sev_est, sev_akt) if s is not None]
    if sevs:
        out["status"] = {0: cfg.AMAN, 1: cfg.SEGERA, 2: cfg.KRITIS}[max(sevs)]
    return out


def fefo_urutan(batch_df: pd.DataFrame) -> pd.DataFrame:
    """Urutkan batch berdasarkan FEFO (First-Expired, First-Out): sisa_efektif terkecil lebih dulu, lalu tanggal_diterima."""
    if batch_df.empty:
        return batch_df.copy()
    d = batch_df.copy()
    d["_sisa_sort"] = pd.to_numeric(d.get("sisa_efektif"), errors="coerce").fillna(1e9)
    d["_tgl_sort"] = pd.to_datetime(d.get("tanggal_diterima"), errors="coerce")
    d = d.sort_values(["_sisa_sort", "_tgl_sort"]).reset_index(drop=True)
    d["urutan_fefo"] = d.groupby(["produk_id", "lokasi"], dropna=False).cumcount() + 1
    return d.drop(columns=["_sisa_sort", "_tgl_sort"])


def expected_waste(batch_df: pd.DataFrame, forecast_harian: float | dict[str, float] | None = None) -> pd.DataFrame:
    """Simulasikan konsumsi FEFO terhadap forecast harian; hitung estimasi kg batch yang melewati masa simpan."""
    if batch_df.empty:
        out = batch_df.copy()
        out["hari_sampai_habis"] = pd.Series(dtype=float)
        out["prob_busuk_konsumsi"] = pd.Series(dtype=float)
        out["estimasi_busuk_kg"] = pd.Series(dtype=float)
        return out

    d = fefo_urutan(batch_df)
    peta_default = {"ayam": 6.08, "lamm": 6.33, "steak": 5.62, "koefte": 3.31}
    if isinstance(forecast_harian, dict):
        peta_fc = {str(k).lower(): float(v) for k, v in forecast_harian.items() if v is not None and float(v) > 0}
    elif isinstance(forecast_harian, (int, float, np.number)) and float(forecast_harian) > 0:
        peta_fc = {"_default": float(forecast_harian)}
    else:
        peta_fc = peta_default

    faktor_kg = d["satuan"].map({"kg": 1.0, "g": 0.001, "liter": 1.0, "ml": 0.001, "porsi": 0.2}).fillna(0.5)
    d["jumlah_kg_setara"] = pd.to_numeric(d["jumlah"], errors="coerce").fillna(0.0) * faktor_kg

    hari_habis_list = []
    prob_list = []
    waste_list = []

    # Kelompokkan per produk_id + lokasi agar antrean FEFO dikonsumsi berurutan
    kumulatif_map: dict[tuple, float] = {}
    for _, r in d.iterrows():
        kunci = (r.get("produk_id"), r.get("lokasi"))
        item_k = str(r.get("item") or "").lower()
        laju = peta_fc.get(item_k, peta_fc.get("_default", peta_default.get(item_k, 2.0)))
        laju = max(0.1, float(laju))

        stok_sebelum = kumulatif_map.get(kunci, 0.0)
        qty_kg = float(r["jumlah_kg_setara"])
        kumulatif_map[kunci] = stok_sebelum + qty_kg
        # Horizon waktu sampai seluruh batch ini habis dikonsumsi
        h_habis = (stok_sebelum + qty_kg) / laju
        hari_habis_list.append(h_habis)

        sisa_eff = r.get("sisa_efektif")
        mn, mx = r.get("min_hari"), r.get("maks_hari")
        umur = float(r.get("umur_hari", 0.0))
        if pd.notna(sisa_eff) and float(sisa_eff) <= 0:
            p_busuk = 1.0
        elif pd.notna(mn) and pd.notna(mx):
            p_busuk = peluang_lewat(umur, float(mn), float(mx), h_habis)
        elif pd.notna(sisa_eff):
            p_busuk = 1.0 if h_habis > float(sisa_eff) else 0.0
        else:
            p_busuk = 0.0

        prob_list.append(p_busuk)
        waste_list.append(qty_kg * p_busuk)

    d["hari_sampai_habis"] = hari_habis_list
    d["prob_busuk_konsumsi"] = prob_list
    d["estimasi_busuk_kg"] = waste_list
    return d


def evaluasi_inventaris(inv: pd.DataFrame, tabel: pd.DataFrame, produk: pd.DataFrame,
                        today: date | None = None, forecast_harian: dict[str, float] | None = None) -> pd.DataFrame:
    """Gabungkan inventaris dengan acuan dataset dan hitung status, FEFO, FIFO, serta expected waste."""
    today = today or date.today()
    kolom_out = ["id", "nama", "produk_id", "item", "produk_acuan", "kategori", "jumlah", "satuan", "lokasi", "suhu_c",
                 "tanggal_diterima", "tanggal_kedaluwarsa_aktual", "catatan", "jenis", "min_hari", "maks_hari",
                 "tengah_hari", "rentang_teks", "umur_hari", "sisa_hari", "tanggal_estimasi", "tanggal_efektif",
                 "sisa_efektif", "status", "catatan_estimasi", "tips"] + [f"p{h}" for h in cfg.HORIZON_HARI] + \
                ["urutan_prioritas", "urutan_fefo", "urutan_fifo", "estimasi_busuk_kg", "rekomendasi"]
    if inv.empty:
        return pd.DataFrame(columns=kolom_out)

    df = inv.copy()
    if "item" not in df.columns:
        df["item"] = None
    # Isi item otomatis bila produk_id cocok dengan pemetaan standar
    peta_balik = {int(v): k for k, v in cfg.ITEM_KE_PRODUK_ID.items()}
    df["item"] = [
        it if (it is not None and not pd.isna(it) and str(it).strip() != "")
        else peta_balik.get(int(pid)) if pd.notna(pid) else None
        for it, pid in zip(df["item"], df["produk_id"])
    ]

    df["tanggal_diterima"] = pd.to_datetime(df["tanggal_diterima"])
    df["tanggal_kedaluwarsa_aktual"] = pd.to_datetime(df["tanggal_kedaluwarsa_aktual"])
    df = df.merge(tabel[["produk_id", "lokasi", "jenis", "min_hari", "maks_hari", "tengah_hari",
                         "rentang_teks", "tips"]], on=["produk_id", "lokasi"], how="left")
    df = df.merge(produk[["produk_id", "label", "kategori"]].rename(columns={"label": "produk_acuan"}),
                  on="produk_id", how="left")
    df["kategori"] = df["kategori"].fillna("Lainnya")
    df["rentang_teks"] = df["rentang_teks"].fillna("—")
    df["tips"] = df["tips"].fillna("")

    ev = df.apply(lambda r: pd.Series(_evaluasi_baris(r, today)), axis=1)
    df = pd.concat([df, ev], axis=1)
    for c in ["umur_hari", "sisa_hari", "sisa_efektif"] + [f"p{h}" for h in cfg.HORIZON_HARI]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["_sev"] = df["status"].map(cfg.STATUS_URUT)
    df["_sisa"] = pd.to_numeric(df["sisa_efektif"], errors="coerce").fillna(1e9)
    # Urutan prioritas utama mengikuti FEFO (sisa efektif terkecil, lalu tanggal diterima)
    df = df.sort_values(["_sev", "_sisa", "tanggal_diterima"]).reset_index(drop=True)
    df["urutan_prioritas"] = np.arange(1, len(df) + 1)
    df["urutan_fefo"] = df.groupby(["produk_id", "lokasi"], dropna=False).cumcount() + 1
    df["urutan_fifo"] = df.groupby(["produk_id", "lokasi"], dropna=False)["tanggal_diterima"].rank(method="first").astype(int)

    df_w = expected_waste(df, forecast_harian=forecast_harian)
    peta_w = dict(zip(df_w["id"], df_w["estimasi_busuk_kg"]))
    df["estimasi_busuk_kg"] = df["id"].map(peta_w).fillna(0.0)
    df["rekomendasi"] = df.apply(_rekomendasi, axis=1)
    return df.drop(columns=["_sev", "_sisa"])[kolom_out]


def _rekomendasi(r: pd.Series) -> str:
    s = r["status"]
    if s == cfg.KRITIS:
        return "Periksa kondisi fisik sekarang. Jika ragu, jangan dikonsumsi (prioritas FEFO #1)."
    if s == cfg.SEGERA:
        sisa = r["sisa_efektif"]
        batas = f" dalam {int(sisa)} hari" if pd.notna(sisa) and sisa > 0 else " hari ini"
        return f"Prioritaskan konsumsi{batas} (FEFO #{int(r['urutan_fefo'])})."
    if s == cfg.AMAN:
        multi = " Gunakan batch ini lebih dulu (FEFO #1)." if r["urutan_fefo"] == 1 else ""
        return "Simpan dengan baik." + multi
    return "Pantau manual dan ikuti tanggal pada kemasan."
