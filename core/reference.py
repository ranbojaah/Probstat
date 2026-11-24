"""Memuat dataset referensi FoodKeeper dan mengubahnya menjadi tabel masa simpan.

Dataset FoodKeeper berisi RENTANG masa simpan (minimum-maksimum) per produk dan
kondisi penyimpanan. Dataset ini TIDAK berisi pengamatan individual pembusukan,
sehingga tidak ada kejadian/sensor yang bisa dipakai untuk Kaplan-Meier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as cfg

JENIS_RENTANG = "rentang"
JENIS_TUNGGAL = "nilai_tunggal"
JENIS_TANPA_BATAS = "tanpa_batas"
JENIS_TIDAK_DISARANKAN = "tidak_disarankan"
JENIS_TANGGAL_KEMASAN = "tanggal_kemasan"
JENIS_SAAT_MATANG = "saat_matang"
JENIS_TIDAK_ADA = "tidak_ada_data"
JENIS_NUMERIK = (JENIS_RENTANG, JENIS_TUNGGAL)

CATATAN_JENIS = {
    JENIS_TANPA_BATAS: "Dataset menyatakan dapat disimpan tanpa batas waktu (aspek kualitas, bukan keamanan).",
    JENIS_TIDAK_DISARANKAN: "Dataset tidak menyarankan penyimpanan di lokasi ini.",
    JENIS_TANGGAL_KEMASAN: "Dataset merujuk pada tanggal pada kemasan. Isi tanggal kedaluwarsa aktual.",
    JENIS_SAAT_MATANG: "Masa simpan bergantung tingkat kematangan; tidak ada angka hari di dataset.",
    JENIS_TIDAK_ADA: "Dataset tidak memuat acuan masa simpan untuk produk dan lokasi ini.",
}

REQUIRED_PRODUCT_COLS = ["ID", "Category_ID", "Name"]


def reference_token() -> tuple:
    """Token perubahan file referensi (dipakai sebagai kunci cache)."""
    def mt(p):
        return p.stat().st_mtime if p.exists() else 0
    return (mt(cfg.USER_PRODUCT), mt(cfg.USER_CATEGORY), mt(cfg.BUNDLED_PRODUCT))


def using_user_reference() -> bool:
    return cfg.USER_PRODUCT.exists() and cfg.USER_CATEGORY.exists()


def validate_reference(product: pd.DataFrame, category: pd.DataFrame) -> list[str]:
    """Kembalikan daftar masalah (kosong bila valid)."""
    masalah = []
    for col in REQUIRED_PRODUCT_COLS:
        if col not in product.columns:
            masalah.append(f"Kolom '{col}' tidak ditemukan pada sheet Product.")
    for col in ("ID", "Category_Name"):
        if col not in category.columns:
            masalah.append(f"Kolom '{col}' tidak ditemukan pada sheet Category.")
    if not any(c.endswith("_Metric") for c in product.columns):
        masalah.append("Kolom satuan waktu (*_Metric) tidak ditemukan. Format FoodKeeper diperlukan.")
    return masalah


def load_reference() -> tuple[pd.DataFrame, pd.DataFrame]:
    if using_user_reference():
        product = pd.read_csv(cfg.USER_PRODUCT)
        category = pd.read_csv(cfg.USER_CATEGORY)
    else:
        product = pd.read_csv(cfg.BUNDLED_PRODUCT)
        category = pd.read_csv(cfg.BUNDLED_CATEGORY)

    cat = category.rename(columns={"ID": "kategori_id", "Category_Name": "kategori_en",
                                   "Subcategory_Name": "subkategori"})
    prod = product.rename(columns={"ID": "produk_id", "Category_ID": "kategori_id", "Name": "nama",
                                   "Name_subtitle": "subtitle", "Keywords": "kata_kunci"})
    prod = prod.merge(cat[["kategori_id", "kategori_en", "subkategori"]], on="kategori_id", how="left")
    prod["kategori"] = prod["kategori_id"].map(cfg.KATEGORI_ID).fillna(prod["kategori_en"]).fillna("Lainnya")
    sub = prod["subtitle"].fillna("").astype(str).str.strip()
    prod["label"] = np.where(sub != "", prod["nama"].astype(str) + " (" + sub + ")", prod["nama"].astype(str))
    return prod, cat


def _pilih_kolom(row: pd.Series, awalan: str) -> tuple[str, str] | None:
    """Pilih kolom acuan: DOP_ (dihitung dari tanggal pembelian) lebih dulu, lalu kolom biasa."""
    for pref in (f"DOP_{awalan}", awalan):
        if pd.notna(row.get(f"{pref}_Metric")):
            return pref, str(row[f"{pref}_Metric"]).strip()
    return None


def _angka(x) -> str:
    return f"{x:g}"


def _parse_satu(row: pd.Series, awalan: str) -> dict:
    hasil = dict(jenis=JENIS_TIDAK_ADA, min_hari=np.nan, maks_hari=np.nan, tengah_hari=np.nan,
                 rentang_teks="—", sumber_kolom="", tips="")
    pil = _pilih_kolom(row, awalan)
    if pil is None:
        return hasil
    pref, metric = pil
    m = metric.lower()
    hasil["sumber_kolom"] = pref
    tips = row.get(f"{pref}_tips", row.get(f"{pref}_Tips", ""))
    hasil["tips"] = "" if pd.isna(tips) else str(tips)

    teks_non = {"indefinitely": (JENIS_TANPA_BATAS, "Tanpa batas"),
                "not recommended": (JENIS_TIDAK_DISARANKAN, "Tidak disarankan"),
                "package use-by date": (JENIS_TANGGAL_KEMASAN, "Ikuti tanggal kemasan"),
                "when ripe": (JENIS_SAAT_MATANG, "Saat matang")}
    if m in teks_non:
        hasil["jenis"], hasil["rentang_teks"] = teks_non[m]
        return hasil
    if m not in cfg.HARI_PER_SATUAN:
        return hasil

    mn, mx = row.get(f"{pref}_Min"), row.get(f"{pref}_Max")
    if pd.isna(mn) and pd.isna(mx):
        return hasil
    if pd.isna(mn):
        mn = mx
    if pd.isna(mx):
        mx = mn
    f = cfg.HARI_PER_SATUAN[m]
    satuan = cfg.SATUAN_ID[m]
    hasil.update(min_hari=float(mn) * f, maks_hari=float(mx) * f, tengah_hari=(float(mn) + float(mx)) / 2 * f)
    if float(mn) == float(mx):
        hasil["jenis"] = JENIS_TUNGGAL
        hasil["rentang_teks"] = f"{_angka(mn)} {satuan}"
    else:
        hasil["jenis"] = JENIS_RENTANG
        hasil["rentang_teks"] = f"{_angka(mn)}–{_angka(mx)} {satuan}"
    return hasil


def build_shelf_life_table(product_raw: pd.DataFrame) -> pd.DataFrame:
    """Tabel panjang: satu baris per (produk, lokasi simpan)."""
    baris = []
    for _, row in product_raw.iterrows():
        for lokasi, awalan in cfg.LOKASI.items():
            d = _parse_satu(row, awalan)
            d.update(produk_id=int(row["produk_id"]), lokasi=lokasi)
            baris.append(d)
    return pd.DataFrame(baris)


def raw_for_table(products: pd.DataFrame) -> pd.DataFrame:
    """Produk (hasil load_reference) sudah memuat kolom mentah; fungsi ini hanya alias agar jelas."""
    return products
