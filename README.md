# Smart Food Inventory & Supply Chain System (FEFO & Perishable Procurement)

Aplikasi Streamlit multi-halaman berbahasa Indonesia untuk mengelola **ketersediaan bahan baku mudah rusak (*perishable food supply chain*)**, memperkirakan masa simpan, mengurutkan konsumsi berbasis **FEFO (*First-Expired, First-Out*)**, merencanakan pengadaan (**Safety Stock Normal & Empiris, Reorder Point, Batas Masa Simpan, Newsvendor**), melakukan **peramalan permintaan**, serta mengevaluasi kebijakan lewat **Backtest & Simulasi Monte Carlo**.

Aplikasi ini menjawab tiga pertanyaan utama:
1. **Bahan tahan berapa hari?** (Dataset USDA FoodKeeper + model probabilitas bersyarat Seragam & Kaplan-Meier)
2. **Kapan harus pesan ulang, dan berapa banyak?** (Pola permintaan hari-dalam-minggu, Safety Stock, ROP, Kalender Restok Bulanan)
3. **Stok maksimum berapa agar tidak busuk?** (Batas stok $S_{\text{cap}}$ dari masa simpan konservatif & simulasi trade-off layanan vs barang terbuang)

## Instalasi dan menjalankan

```powershell
cd d:\TUGAS\Projek\smart_food_app
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Buka **http://localhost:8501**. Data tersimpan otomatis di `storage/inventaris.db` (SQLite). Disarankan Python 3.10–3.13.

## Struktur proyek

```text
app.py                      Titik masuk, navigasi 10 halaman, tema
config.py                   Konstanta, pemetaan ITEM_KE_PRODUK_ID, GRAM_PER_PORSI, sitasi
nav.py                      Registri halaman
core/
  reference.py              Memuat USDA FoodKeeper, konversi rentang ke hari
  shelf_life.py             Status masa simpan, probabilitas Seragam, urutan FEFO, expected_waste
  permintaan.py             Memuat & memvalidasi permintaan harian, konversi kg, indeks musiman bulanan
  procurement.py            Parameter per hari (Mode Data & Manual), SS Normal & Empiris, ROP, S_cap, Newsvendor
  forecast.py               Naif musiman 4 minggu, Rata-rata hari × indeks bulan, Holt-Winters, rolling-origin
  simulasi.py               Backtest (760 hari) & Monte Carlo (>=1.000 hari) untuk Kebijakan A, B, dan C
  stats.py                  Deskriptif, Shapiro-Wilk, Kruskal-Wallis, Wilcoxon, CI Wilson, Kaplan-Meier, Cox PH
  historical.py             Validasi data historis pembusukan
  reports.py                Generator CSV (pengadaan, inventaris FEFO, statistik) dan PDF laporan lengkap
  cache.py                  Pemuat cache Streamlit
database/db.py              SQLite (inventaris, permintaan, pemasok, pemasok_item, parameter_item, pesanan, historis)
ui/                         CSS sistem desain, komponen, kotak transparansi asumsi, pembentuk tabel
views/                      Dashboard, Inventaris (FEFO), Permintaan & Peramalan, Perencanaan Pengadaan,
                            Simulasi & Evaluasi, Pemasok, Prediksi Masa Simpan, Analisis Statistik, Dataset, Laporan
data/                       FoodKeeper-Data.xls + CSV hasil ekstraksi + permintaan_harian_restoran.csv (760 hari)
tests/test_core.py          16 gugus unit test logika inti & supply chain
```

## Dua Mode Bahan Baku (Mode Data vs Mode Manual)

| Mode | Bahan | Sumber Parameter | Label di Aplikasi |
|---|---|---|---|
| **Mode Data** | Ayam (`HAEHNCHEN`), Domba (`LAMM`), Daging Sapi (`STEAK`), Daging Giling (`KOEFTE`), Daging Total | Dataset permintaan harian restoran (760 hari) | `Berbasis data` |
| **Mode Manual** | Seluruh 661 produk lain di USDA FoodKeeper | Diisi pengguna (`mean_kg_hari`, `cv` default 0,30) | `Berbasis asumsi pengguna` |

Jika pengguna mengunggah data permintaan harian untuk bahan bermode manual di halaman **Dataset**, bahan tersebut otomatis berpindah ke **Mode Data**.

## Transparansi Asumsi & Keterbatasan Data

1. **Asumsi konversi porsi ke kg:** Dataset permintaan asli hanya memuat satuan **porsi**. Konversi ke kilogram menggunakan asumsi yang dapat diubah pengguna (`ayam: 200 g`, `lamm: 200 g`, `steak: 250 g`, `koefte: 150 g`) dan selalu dilabeli *"Konversi menggunakan asumsi gram per porsi"*.
2. **Konteks geografis & durasi:** Data permintaan berasal dari restoran di Stuttgart, Jerman (4 Okt 2013 – 7 Nov 2015, 760 hari). Karena hanya mencakup ±2 tahun, pola hari-dalam-minggu sangat kuat ($p \ll 0{,}001$), sedangkan indeks musiman bulanan bersifat indikatif dan tidak memuat efek Ramadan/Lebaran tanpa input **faktor event manual**.
3. **Parameter biaya & pemasok:** Harga per kg, biaya kurang stok ($C_u$), biaya barang busuk ($C_o$), dan *lead time* pemasok adalah parameter konfigurasi/simulasi.

## Sitasi Dataset

- **Dataset Permintaan Harian (CC BY 4.0):**  
  Taigel, F., & Meller, J. (2020). *Data for: Machine learning for inventory management: Analyzing two concepts to get from data to decisions*. Mendeley Data, V1. https://doi.org/10.17632/7s3ys9ntnz.1
- **Dataset Acuan Masa Simpan:**  
  U.S. Department of Agriculture (USDA) Food Safety and Inspection Service — *FoodKeeper Data*.
