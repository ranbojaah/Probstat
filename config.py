"""Konfigurasi dan konstanta aplikasi.

Semua angka ambang di sini adalah ATURAN KLASIFIKASI (bukan nilai statistik).
Nilai statistik selalu dihitung dari dataset.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

DB_PATH = STORAGE_DIR / "inventaris.db"
BUNDLED_PRODUCT = DATA_DIR / "foodkeeper_product.csv"
BUNDLED_CATEGORY = DATA_DIR / "foodkeeper_category.csv"
BUNDLED_PERMINTAAN = DATA_DIR / "permintaan_harian_restoran.csv"
USER_PRODUCT = STORAGE_DIR / "ref_product.csv"
USER_CATEGORY = STORAGE_DIR / "ref_category.csv"

APP_NAME = "Smart Food Inventory & Supply Chain"

# Pemetaan item restoran (dataset Mendeley) -> produk FoodKeeper (ID dari sheet Product)
ITEM_KE_PRODUK_ID = {
    "ayam": 118,    # Chicken parts - legs or thighs (Kulkas 1-2 hari, Freezer 9 bulan)
    "lamm": 51,     # Lamb - chops, ribs, or loin (Kulkas 3-5 hari, Freezer 4-12 bulan)
    "steak": 40,    # Beef - steaks (Kulkas 3-5 hari, Freezer 4-12 bulan)
    "koefte": 43,   # Beef - ground (Kulkas 1-2 hari, Freezer 3-4 bulan)
}

ITEM_LABEL = {
    "ayam": "Ayam (Haehnchen)",
    "lamm": "Domba (Lamm)",
    "steak": "Daging Sapi (Steak)",
    "koefte": "Daging Giling (Koefte)",
    "daging": "Daging Total (Lamb + Steak + Koefte)",
}

# Asumsi konversi porsi -> gram (bisa diubah pengguna; wajib dilabeli asumsi)
GRAM_PER_PORSI = {"ayam": 200.0, "lamm": 200.0, "steak": 250.0, "koefte": 150.0}
CV_DEFAULT_MANUAL = 0.30
TINGKAT_LAYANAN_DEFAULT = 0.95
LEAD_TIME_DEFAULT = 1.0
HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

SITASI_MENDELEY = (
    "Taigel, F., & Meller, J. (2020). Data for: Machine learning for inventory management: "
    "Analyzing two concepts to get from data to decisions. Mendeley Data, V1. "
    "https://doi.org/10.17632/7s3ys9ntnz.1 (CC BY 4.0)."
)
SITASI_USDA = "U.S. Department of Agriculture (USDA) Food Safety and Inspection Service — FoodKeeper Data."

# Lokasi simpan (tampilan Indonesia) -> awalan kolom di dataset FoodKeeper
LOKASI = {"Suhu Ruang": "Pantry", "Kulkas": "Refrigerate", "Freezer": "Freeze"}
SATUAN = ["kg", "g", "liter", "ml", "buah", "bungkus", "kaleng", "botol", "porsi"]

# Konversi satuan waktu dataset ke hari. Bulan = 30 hari, tahun = 365 hari (pendekatan).
HARI_PER_SATUAN = {"hours": 1 / 24, "days": 1, "weeks": 7, "months": 30, "years": 365, "year": 365}
SATUAN_ID = {"hours": "jam", "days": "hari", "weeks": "minggu", "months": "bulan", "years": "tahun", "year": "tahun"}

# Status
AMAN = "Aman"
SEGERA = "Segera Dikonsumsi"
KRITIS = "Kritis"
BELUM = "Belum Dapat Diestimasi"
STATUS_URUT = {KRITIS: 0, SEGERA: 1, AMAN: 2, BELUM: 3}
STATUS_WARNA = {AMAN: "#16A34A", SEGERA: "#D97706", KRITIS: "#DC2626", BELUM: "#6B7280"}
STATUS_LATAR = {AMAN: "#DCFCE7", SEGERA: "#FEF3C7", KRITIS: "#FEE2E2", BELUM: "#F3F4F6"}

# Aturan status
SEGERA_FRAKSI = 0.25        # "Segera" jika sisa masa simpan <= 25% dari estimasi tengah (min. 1 hari)
SEGERA_HARI_AKTUAL = 3      # "Segera" jika tanggal kedaluwarsa kemasan <= 3 hari lagi
HORIZON_HARI = (1, 3, 5, 7)
RISIKO_TINGGI_HORIZON = 3   # Berisiko tinggi: P(melewati masa simpan dalam 3 hari) >= 50%
RISIKO_TINGGI_AMBANG = 0.5

# Analisis survival
MIN_KEJADIAN_KM = 10        # minimal kejadian pembusukan agar Kaplan-Meier dipakai
KEJADIAN_PER_KOVARIAT = 10  # aturan praktis untuk Cox PH
BOOTSTRAP_ULANG = 300
BOOTSTRAP_SEED = 42         # hanya untuk reprodusibilitas hasil resampling

KATEGORI_ID = {
    1: "Makanan Bayi", 2: "Roti & Kue", 3: "Roti & Kue", 4: "Roti & Kue", 5: "Minuman",
    6: "Bumbu, Saus & Kaleng", 7: "Susu & Telur", 8: "Makanan Beku",
    9: "Biji-bijian, Kacang & Pasta", 10: "Daging", 11: "Daging", 12: "Daging", 13: "Daging",
    14: "Unggas", 15: "Unggas", 16: "Unggas", 17: "Unggas", 18: "Buah Segar", 19: "Sayuran Segar",
    20: "Makanan Laut", 21: "Makanan Laut", 22: "Makanan Laut", 23: "Makanan Tahan Lama",
    24: "Protein Nabati", 25: "Deli & Siap Saji",
}

BULAN_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

DISCLAIMER = (
    "Estimasi ini dihitung dari rentang acuan dataset dan bukan jaminan keamanan pangan. "
    "Selalu periksa kondisi bahan (bau, warna, tekstur) dan ikuti tanggal kedaluwarsa pada kemasan."
)
