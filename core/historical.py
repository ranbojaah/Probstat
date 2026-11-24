"""Validasi dan pra-pemrosesan data historis (observasi masa simpan) yang diunggah pengguna."""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

POLA_KOLOM = {
    "durasi": r"durasi|duration|lama|days|hari|time|shelf",
    "kejadian": r"event|kejadian|spoil|busuk|rusak|status|observed|censor",
    "lokasi": r"storage|lokasi|simpan|penyimpanan|condition|kondisi",
    "suhu": r"temp|suhu",
    "kategori": r"categor|kategori|jenis|type|kelompok",
    "nama": r"name|nama|product|produk|bahan|item",
    "mulai": r"start|mulai|received|diterima|purchase|beli",
    "akhir": r"end|akhir|selesai|spoiled_date|observ",
}
LABEL_KOLOM = {
    "nama": "Nama bahan", "kategori": "Kategori", "lokasi": "Lokasi/kondisi simpan", "suhu": "Suhu simpan (°C)",
    "durasi": "Durasi hingga kejadian/akhir pengamatan (hari)", "kejadian": "Kejadian (1 = busuk/rusak, 0 = tersensor)",
    "mulai": "Tanggal mulai (opsional)", "akhir": "Tanggal akhir (opsional)",
}
YA = {"1", "ya", "y", "yes", "true", "t", "busuk", "rusak", "spoiled", "spoil", "expired", "event"}
TIDAK = {"0", "tidak", "no", "n", "false", "f", "tersensor", "censored", "fresh", "baik", "ok"}


def baca_unggahan(nama: str, data: bytes) -> pd.DataFrame:
    """Baca CSV/Excel. Melempar ValueError dengan pesan Indonesia bila gagal."""
    low = nama.lower()
    try:
        if low.endswith((".xlsx", ".xlsm")):
            return pd.read_excel(io.BytesIO(data), engine="openpyxl")
        if low.endswith(".xls"):
            try:
                return pd.read_excel(io.BytesIO(data), engine="xlrd")
            except ImportError as e:
                raise ValueError("Membaca file .xls membutuhkan paket 'xlrd'. Instal lewat requirements.txt "
                                 "atau simpan file sebagai .xlsx/.csv.") from e
        if low.endswith((".csv", ".txt", ".tsv")):
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    return pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding=enc)
                except UnicodeDecodeError:
                    continue
            raise ValueError("Encoding file tidak dikenali. Simpan ulang sebagai UTF-8.")
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"File tidak dapat dibaca: {e}") from e
    raise ValueError("Format file tidak didukung. Gunakan CSV, XLS, atau XLSX.")


def tebak_pemetaan(df: pd.DataFrame) -> dict[str, str | None]:
    hasil: dict[str, str | None] = {k: None for k in POLA_KOLOM}
    dipakai: set[str] = set()
    for kunci in ("kejadian", "durasi", "suhu", "lokasi", "kategori", "nama", "mulai", "akhir"):
        for col in df.columns:
            if col in dipakai:
                continue
            if re.search(POLA_KOLOM[kunci], str(col), flags=re.I):
                hasil[kunci] = col
                dipakai.add(col)
                break
    return hasil


def normalisasi_lokasi(x) -> str | float:
    if pd.isna(x):
        return np.nan
    s = str(x).strip().lower()
    if re.search(r"freez|frozen|beku", s):
        return "Freezer"
    if re.search(r"refrig|fridge|kulkas|lemari es|chill|dingin", s):
        return "Kulkas"
    if re.search(r"pantry|room|ruang|lemari|ambient|shelf", s):
        return "Suhu Ruang"
    return str(x).strip().title()


def _ke_kejadian(serie: pd.Series) -> pd.Series:
    def f(v):
        if pd.isna(v):
            return np.nan
        s = str(v).strip().lower()
        if s in ("1", "1.0"):
            return 1
        if s in ("0", "0.0"):
            return 0
        if s in YA:
            return 1
        if s in TIDAK:
            return 0
        return np.nan
    return serie.map(f)


def ringkasan_info(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Kolom": df.columns, "Tipe data": [str(t) for t in df.dtypes],
                         "Terisi": df.notna().sum().values, "Kosong": df.isna().sum().values,
                         "Kosong (%)": (df.isna().mean().values * 100).round(1),
                         "Nilai unik": [df[c].nunique(dropna=True) for c in df.columns]})


def praproses(df: pd.DataFrame, peta: dict[str, str | None]) -> tuple[pd.DataFrame, dict]:
    """Bersihkan data dan hasilkan tabel standar. Tidak ada nilai yang dikarang:
    baris yang tidak valid dibuang dan dicatat pada laporan."""
    lap = dict(baris_awal=len(df), dibuang={}, peringatan=[], galat=[])
    out = pd.DataFrame(index=df.index)

    if peta.get("durasi"):
        out["durasi_hari"] = pd.to_numeric(df[peta["durasi"]], errors="coerce")
    elif peta.get("mulai") and peta.get("akhir"):
        a = pd.to_datetime(df[peta["mulai"]], errors="coerce")
        b = pd.to_datetime(df[peta["akhir"]], errors="coerce")
        out["durasi_hari"] = (b - a).dt.total_seconds() / 86400
    else:
        lap["galat"].append("Pilih kolom durasi, atau pasangan kolom tanggal mulai dan tanggal akhir.")
    if not peta.get("kejadian"):
        lap["galat"].append("Pilih kolom kejadian (1 = busuk/rusak, 0 = tersensor).")
    if lap["galat"]:
        return pd.DataFrame(), lap

    out["kejadian"] = _ke_kejadian(df[peta["kejadian"]])
    out["nama"] = df[peta["nama"]].astype(str).str.strip() if peta.get("nama") else np.nan
    out["kategori"] = df[peta["kategori"]].astype(str).str.strip() if peta.get("kategori") else np.nan
    out["lokasi"] = df[peta["lokasi"]].map(normalisasi_lokasi) if peta.get("lokasi") else np.nan
    out["suhu_c"] = pd.to_numeric(df[peta["suhu"]], errors="coerce") if peta.get("suhu") else np.nan

    n0 = len(out)
    bad = out["durasi_hari"].isna()
    lap["dibuang"]["Durasi kosong/bukan angka"] = int(bad.sum())
    out = out[~bad]
    bad = out["durasi_hari"] <= 0
    lap["dibuang"]["Durasi nol atau negatif"] = int(bad.sum())
    out = out[~bad]
    bad = out["kejadian"].isna()
    lap["dibuang"]["Nilai kejadian tidak dikenali"] = int(bad.sum())
    out = out[~bad].copy()
    out["kejadian"] = out["kejadian"].astype(int)
    out = out.reset_index(drop=True)

    lap["baris_valid"] = len(out)
    lap["kejadian"] = int(out["kejadian"].sum())
    lap["tersensor"] = int(len(out) - out["kejadian"].sum())
    if n0 and len(out) / n0 < 0.7:
        lap["peringatan"].append("Lebih dari 30% baris dibuang. Periksa pemetaan kolom.")
    if len(out) == 0:
        lap["galat"].append("Tidak ada baris valid setelah pembersihan.")
    elif lap["kejadian"] < 1:
        lap["peringatan"].append("Tidak ada kejadian pembusukan. Kaplan-Meier tidak dapat dihitung.")
    elif lap["kejadian"] < 10:
        lap["peringatan"].append(f"Hanya {lap['kejadian']} kejadian. Hasil survival belum cukup andal "
                                 "dan tidak akan dipakai untuk prediksi.")
    if peta.get("suhu") and out["suhu_c"].isna().mean() > 0.2:
        lap["peringatan"].append("Lebih dari 20% suhu kosong. Suhu tidak akan dipakai pada model Cox.")
    return out, lap


def buat_contoh_historis() -> pd.DataFrame:
    """Buat dataset observasi historis contoh (72 baris) untuk simulasi Kaplan-Meier, Log-rank, dan Cox PH."""
    rng = np.random.default_rng(42)
    baris = []
    # (nama, kategori, lokasi, suhu_rata, skala_hari, n_obs)
    skenario = [
        ("Ayam potong", "Unggas", "Kulkas", 4.2, 3.5, 10),
        ("Susu segar", "Susu & Telur", "Kulkas", 4.5, 6.5, 8),
        ("Bayam & sawi", "Sayuran Segar", "Kulkas", 5.0, 5.0, 8),
        ("Daging sapi", "Daging", "Kulkas", 3.8, 4.5, 8),
        ("Pisang & tomat", "Buah Segar", "Suhu Ruang", 27.5, 4.0, 10),
        ("Roti tawar", "Roti & Kue", "Suhu Ruang", 26.8, 5.5, 8),
        ("Sayur suhu ruang", "Sayuran Segar", "Suhu Ruang", 28.0, 2.5, 6),
        ("Ayam beku", "Unggas", "Freezer", -17.5, 35.0, 7),
        ("Daging beku", "Daging", "Freezer", -18.0, 45.0, 7),
    ]
    for nama, kat, lok, suhu_mu, skala, n_obs in skenario:
        for _ in range(n_obs):
            suhu = round(float(rng.normal(suhu_mu, 1.2)), 1)
            # Suhu lebih tinggi sedikit mempercepat pembusukan
            faktor = np.exp(-0.04 * (suhu - suhu_mu))
            waktu_rusak = max(1.0, round(float(rng.weibull(2.2) * skala * faktor), 1))
            waktu_sensor = max(1.0, round(float(rng.uniform(0.6 * skala, 1.8 * skala)), 1))
            if waktu_rusak <= waktu_sensor:
                durasi, kej = waktu_rusak, 1
            else:
                durasi, kej = waktu_sensor, 0
            baris.append(dict(nama=nama, kategori=kat, lokasi=lok, suhu_c=suhu,
                              durasi_hari=durasi, kejadian=kej))
    return pd.DataFrame(baris)


def template_historis_csv() -> bytes:
    """CSV contoh/template siap unduh."""
    contoh = buat_contoh_historis().head(15)
    return contoh.to_csv(index=False).encode("utf-8-sig")
