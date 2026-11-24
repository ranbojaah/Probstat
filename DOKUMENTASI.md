# Dokumentasi Lengkap: Smart Food Inventory & Supply Chain System

## 1. Gambaran Umum & Tujuan Aplikasi

**Smart Food Inventory & Supply Chain System** adalah aplikasi web multi-halaman berbasis **Streamlit (Python)** berbahasa Indonesia untuk mengelola **ketersediaan bahan baku mudah rusak (*perishable food supply chain*)**, memantau masa simpan dengan aturan **FEFO (*First-Expired, First-Out*)**, serta menerapkan metode **Probabilitas dan Statistika** secara nyata dan transparan.

Aplikasi ini menjawab tiga pertanyaan utama:
1. **Bahan tahan berapa hari?** — Dihitung dari rentang masa simpan dataset **USDA FoodKeeper**, probabilitas bersyarat Distribusi Seragam, serta analisis survival **Kaplan-Meier** bila data observasi pembusukan tersedia.
2. **Kapan harus pesan ulang, dan berapa banyak?** — Dihitung spesifik **per hari dalam minggu** menggunakan rata-rata & simpangan baku permintaan harian, **Safety Stock** (pendekatan Normal skor-$z$ dan **Kuantil Empiris** berdampingan), **Reorder Point (ROP)**, target stok *periodic review* ($S$), model **Newsvendor**, serta **Kalender Restok Bulanan**.
3. **Stok maksimum berapa agar tidak busuk?** — Dibatasi oleh kapasitas pemakaian selama masa simpan konservatif ($S_{\text{cap}}$), dilengkapi estimasi barang terbuang (*expected waste*) dan evaluasi *trade-off* kuantitatif lewat **Backtest & Simulasi Monte Carlo**.

### Ukuran Keberhasilan (KPI Utama)
| KPI | Definisi | Target Awal |
|---|---|---|
| **Tingkat Layanan (*Cycle Service Level*)** | Persentase hari tanpa kehabisan stok | $\ge 95\%$ |
| **Fill Rate** | Persentase total volume permintaan yang terpenuhi dari stok | $\ge 98\%$ |
| **Barang Terbuang (*Expected / Simulated Waste*)** | Kilogram bahan yang melewati batas masa simpan | Seminal mungkin |
| **Rata-rata Stok** | Rata-rata kg stok di penyimpanan | Seminal mungkin pada target layanan |

---

## 2. Ruang Lingkup Bahan: Mode Data vs Mode Manual

| Mode | Cakupan Bahan | Sumber Parameter Permintaan | Lencana di Aplikasi |
|---|---|---|---|
| **Mode Data** | Ayam (`ayam`), Domba (`lamm`), Daging Sapi (`steak`), Daging Giling (`koefte`), dan Daging Total (`daging`) | Dataset permintaan harian restoran Mendeley (760 hari) | `Berbasis data` |
| **Mode Manual** | Seluruh 661 produk lain pada USDA FoodKeeper (sayur, susu, telur, seafood, tahu, dll.) | Diisi pengguna: `mean_kg_hari` dan `cv` (default $0{,}30$) | `Berbasis asumsi pengguna` |

- Pada **Mode Manual**, simpangan baku dihitung sebagai $s = \text{CV} \times \text{mean}$ (default $\text{CV} = 0{,}30$ diturunkan dari variasi permintaan daging per hari pada dataset restoran: ayam $0{,}26\text{–}0{,}36$, daging $0{,}19\text{–}0{,}29$).
- Tanpa riwayat permintaan, Mode Manual tidak melakukan perbandingan metode *forecasting* dan tidak menerapkan indeks musiman bulanan (permintaan dianggap datar kecuali pengguna mencentang *"Pakai profil hari dari data daging"* atau menambahkan *faktor event*).
- Jika pengguna mengunggah CSV permintaan harian untuk bahan bermode manual di halaman **Dataset**, bahan tersebut otomatis berpindah ke **Mode Data**.

---

## 3. Dataset yang Digunakan & Transparansi Asumsi

### 3.1 Dataset Masa Simpan: USDA FoodKeeper (`data/FoodKeeper-Data.xls`)
- Berisi **661 produk** dalam **25 kategori** ($\times 3$ lokasi = **1.983 kombinasi produk-lokasi**).
- Pemetaan standar item restoran ke produk FoodKeeper (`config.ITEM_KE_PRODUK_ID`, dapat diubah di halaman **Dataset**):
  - `ayam` (`HAEHNCHEN`) $\to$ ID **118** (*Chicken parts – legs or thighs*: Kulkas 1–2 hari, Freezer 9 bulan)
  - `lamm` (`LAMM`) $\to$ ID **51** (*Lamb – chops, ribs, or loin*: Kulkas 3–5 hari, Freezer 4–12 bulan)
  - `steak` (`STEAK`) $\to$ ID **40** (*Beef – steaks*: Kulkas 3–5 hari, Freezer 4–12 bulan)
  - `koefte` (`KOEFTE`) $\to$ ID **43** (*Beef – ground*: Kulkas 1–2 hari, Freezer 3–4 bulan)

### 3.2 Dataset Permintaan Harian: Mendeley Data (`data/permintaan_harian_restoran.csv`)
- **Sitasi (CC BY 4.0):** Taigel, F., & Meller, J. (2020). *Data for: Machine learning for inventory management: Analyzing two concepts to get from data to decisions*. Mendeley Data, V1. https://doi.org/10.17632/7s3ys9ntnz.1
- **Cakupan:** 4 Oktober 2013 – 7 November 2015 (**760 hari**), restoran di Stuttgart, Jerman, tanpa nilai kosong (`0` missing value), dengan 3 celah tanggal (kemungkinan restoran tutup; dicatat tanpa imputasi/pengisian nilai karangan).
- **Statistik Acuan (Porsi/Hari):**
  - Ayam: rata-rata **30,40**, simpangan baku **11,95** (Min 0, Maks 93; Sabtu **46,55** vs Minggu **21,00** porsi).
  - Lamb: rata-rata **31,64**, simpangan baku **12,65** (Min 0, Maks 88).
  - Steak: rata-rata **22,48**, simpangan baku **9,95** (Min 1, Maks 82).
  - Koefte: rata-rata **22,09**, simpangan baku **9,27** (Min 2, Maks 71).
  - Daging Total (`lamm + steak + koefte`): rata-rata **76,21**, simpangan baku **27,23**.

### 3.3 Asumsi Konversi Porsi $\to$ Kilogram
Dataset asli memuat satuan **porsi**. Konversi ke kilogram menggunakan asumsi default (`config.GRAM_PER_PORSI`, dapat diubah pengguna):
- Ayam: **200 g/porsi** (rata-rata **6,08 kg/hari**; ROP Sabtu pada $L=1, z=1{,}645 \approx \mathbf{13{,}3\text{ kg}}$)
- Lamb: **200 g/porsi**
- Steak: **250 g/porsi**
- Koefte: **150 g/porsi** (rata-rata Daging Total **15,26 kg/hari**)

---

## 4. Arsitektur & Struktur Proyek

```text
smart_food_app/
├── app.py                      # Titik masuk Streamlit & registrasi 10 halaman navigasi
├── config.py                   # Konstanta, ITEM_KE_PRODUK_ID, GRAM_PER_PORSI, sitasi
├── nav.py                      # Registri halaman (PAGES)
├── core/
│   ├── reference.py            # Parser dataset USDA FoodKeeper
│   ├── shelf_life.py           # Evaluasi status masa simpan, probabilitas Seragam, FEFO, expected_waste
│   ├── permintaan.py           # Loader CSV permintaan (YYYY-MM-DD & M.D.YYYY), ke_kg, laporan_kualitas, indeks bulanan
│   ├── procurement.py          # Parameter per hari (Data & Manual), SS Normal & Empiris, ROP, S, S_cap, q, Newsvendor
│   ├── forecast.py             # Naif musiman 4 minggu, Hari × Indeks Bulan, Holt-Winters, evaluasi rolling-origin
│   ├── simulasi.py             # Backtest & Monte Carlo (>=1.000 hari) Kebijakan A, B, dan C dengan FEFO
│   ├── stats.py                # Deskriptif, Shapiro-Wilk, Kruskal-Wallis, Wilcoxon, CI Wilson, Kaplan-Meier, Cox PH
│   ├── historical.py           # Validasi data historis pembusukan
│   ├── reports.py              # Ekspor CSV & PDF laporan lengkap
│   └── cache.py                # Pemuat cache Streamlit
├── database/db.py              # Operasi SQLite (inventaris, permintaan, pemasok, pemasok_item, parameter_item, pesanan, faktor_event, historis)
├── ui/                         # CSS, komponen UI, lencana sumber, kotak transparansi asumsi, pembentuk tabel
├── views/                      # 10 halaman Streamlit
├── data/                       # FoodKeeper-Data.xls, CSV ekstraksi, permintaan_harian_restoran.csv
└── tests/test_core.py          # 16 unit test verifikasi angka dataset & logika pengadaan
```

---

## 5. Penjelasan 10 Halaman Aplikasi

1. **Dashboard Ketersediaan (`views/dashboard.py`):** Menampilkan 5 KPI utama (bahan di bawah ROP, berisiko habis 1–3 hari, batch Kritis, perkiraan barang terbuang FEFO, target layanan), tabel *"Perlu Dipesan Hari Ini"* dengan tombol buat pesanan otomatis, grafik Stok vs ROP vs Batas Masa Simpan ($S_{\text{cap}}$), dan daftar prioritas konsumsi **FEFO**.
2. **Inventaris Bahan (`views/inventaris.py`):** CRUD batch inventaris dengan pengaitan ke item pengadaan, urutan konsumsi **FEFO** (*First-Expired, First-Out*), estimasi barang terbuang per batch, panel **Terima Pesanan** dari pemasok, serta tombol *Habis Dipakai (Tersensor)* dan *Catat Busuk (Kejadian)*.
3. **Permintaan & Peramalan (`views/permintaan.py`):** Laporan kualitas data (760 hari, 3 celah tanggal tanpa imputasi, outlier IQR), uji Shapiro-Wilk, rata-rata per hari-dalam-minggu dengan CI 95% & uji Kruskal-Wallis ($p \ll 0{,}001$), indeks musiman bulanan terkoreksi hari, evaluasi rolling-origin 3 metode peramalan (**MAE, RMSE, sMAPE**), faktor event manual, dan ramalan 14 hari.
4. **Perencanaan Pengadaan (`views/pengadaan.py` — Halaman Inti):** Mendukung **Mode Data** dan **Mode Manual** (untuk seluruh 661 produk FoodKeeper). Menampilkan tabel parameter per hari-dalam-minggu (Mean, Std, **SS Normal & SS Empiris berdampingan**, ROP, Target Stok $S$, Batas Masa Simpan $S_{\text{cap}}$, Jumlah Pesan $q$, Layanan Efektif), peringatan bila $S > S_{\text{cap}}$ atau masa simpan $< L+R$, **Kalender Restok Bulanan**, **Model Newsvendor**, dan expander **Rumus LaTeX + Substitusi Angka**.
5. **Simulasi & Evaluasi (`views/simulasi.py`):** Membandingkan **Kebijakan A (Naif)**, **Kebijakan B (ROP + SS tanpa batas masa simpan)**, dan **Kebijakan C (ROP + SS + Batas Masa Simpan $S_{\text{cap}}$)** lewat Backtest 760 hari maupun Monte Carlo $\ge 1.000$ hari (seed tetap = 42), lengkap dengan **CI Wilson 95%** untuk `% Hari Kehabisan Stok` dan kurva *trade-off* layanan vs barang terbuang.
6. **Pemasok (`views/pemasok.py`):** CRUD master pemasok (*lead time* rata-rata, simpangan baku *lead time*, keandalan), pengaturan harga & MOQ per item, serta pengelolaan pesanan pembelian.
7. **Prediksi Masa Simpan (`views/prediksi.py`):** Detail masa simpan per batch, probabilitas bersyarat melewati masa simpan (1, 3, 5, 7 hari) beserta tabel substitusi rumus Distribusi Seragam, dan panel Kaplan-Meier (ditampilkan bila data historis pembusukan tersedia).
8. **Analisis Statistik (`views/statistik.py`):** Statistik deskriptif dataset FoodKeeper (Q1, Q3, IQR, Skewness, Shapiro-Wilk), proporsi CI Wilson per kategori, uji Kruskal-Wallis & Wilcoxon antar lokasi simpan, serta analisis survival Kaplan-Meier & Cox PH.
9. **Dataset (`views/dataset.py`):** Unggah/reset dataset permintaan harian Mendeley, unggah permintaan bahan spesifik (otomatis memindahkan Mode Manual $\to$ Mode Data), konfigurasi parameter bahan & asumsi gram per porsi, pemetaan item $\to$ produk FoodKeeper, serta data historis pembusukan.
10. **Laporan (`views/laporan.py`):** Unduh **CSV Rencana Pengadaan**, **CSV Inventaris FEFO**, **CSV Statistik Masa Simpan**, dan **PDF Laporan Lengkap**.

---

## 6. Rumus Probabilitas, Statistika & Supply Chain yang Diterapkan

- **Safety Stock (Normal & Lead Time Acak):**
  $$SS_{\text{norm}} = z\sqrt{L\,s_h^2 + \bar{d}_h^2\,s_L^2}, \qquad z = \Phi^{-1}(\text{tingkat layanan})$$
- **Safety Stock (Kuantil Empiris Non-Parametrik):**
  $$r_t = \frac{d_t}{\bar{d}_{h(t)}}, \qquad SS_{\text{emp}} = \max\bigl(0,\ Q_{\alpha}(r) - 1\bigr)\,\bar{d}_h\sqrt{L}$$
- **Reorder Point (ROP):**
  $$ROP_h = \bar{d}_h L + SS$$
- **Target Stok Periodic Review ($S$) & Batas Masa Simpan ($S_{\text{cap}}$):**
  $$S = \sum_{t=1}^{L+R}\hat{d}_t + z\,s_h\sqrt{L+R}, \qquad S_{\text{cap}} = \sum_{t=1}^{m}\hat{d}_t$$
- **Kuantitas Pesan ($q$):**
  $$q = \max\Bigl(0,\ \min(S, S_{\text{cap}}) - I - I_{\text{pipeline}}\Bigr)$$
- **Model Newsvendor (Satu Periode Perishable):**
  $$CR = \frac{C_u}{C_u + C_o}, \qquad Q^* = \bar{d}_h + z_{CR}\,s_h$$
- **Indeks Musiman Bulanan Terkoreksi Hari:**
  $$I_m = \frac{\text{rata-rata } (d_t / \bar{d}_{h(t)}) \text{ pada bulan } m}{\text{rata-rata keseluruhan } (d_t / \bar{d}_{h(t)})}$$
- **Probabilitas Bersyarat Masa Simpan (Distribusi Seragam):**
  $$P(a < T \le a + h \mid T > a) = \frac{F(a+h) - F(a)}{1 - F(a)}, \qquad F(t) = \text{clip}\!\left(\frac{t - a_{\min}}{b_{\max} - a_{\min}},\; 0,\; 1\right)$$

---

## 7. Pengujian Otomatis (`tests/test_core.py`)

Jalankan seluruh 16 unit test dengan:
```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_core.py
```
atau tanpa `pytest`:
```powershell
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'tests'); import test_core as t; [ (getattr(t,n)(), print('PASS',n)) for n in sorted(dir(t)) if n.startswith('test_') ]"
```

---

## 8. Batasan & Ruang Lingkup Saat Ini

1. **Cakupan Supply Chain Perishable:** Aplikasi kini telah mencakup perencanaan pengadaan bahan baku mudah rusak (*Safety Stock* Normal & Empiris per hari-dalam-minggu, *Reorder Point*, batas stok masa simpan $S_{\text{cap}}$, peramalan 3 metode, model *Newsvendor*, manajemen pemasok, serta simulasi *backtest* & Monte Carlo).
2. **Konteks Data Permintaan (Jerman, ±2 Tahun):** Dataset permintaan harian berasal dari restoran di Stuttgart, Jerman (2013–2015). Pola hari-dalam-minggu sangat kuat dan valid untuk demonstrasi metodologi, namun indeks musiman bulanan hanya didasarkan pada ±2 tahun data (bersifat indikatif) dan tidak memuat pola hari besar di Indonesia (Ramadan, Lebaran, Idul Adha) kecuali pengguna menambahkan **Faktor Event Manual**.
3. **Asumsi Konversi, Harga & Mode Manual:** Konversi porsi ke kilogram (`gram_per_porsi`), harga bahan, biaya risiko ($C_u, C_o$), *lead time* pemasok, serta parameter permintaan pada bahan **Mode Manual** merupakan asumsi pengguna/konfigurasi dan selalu diberi lencana penanda secara terbuka di seluruh halaman dan laporan.
4. **Bukan Jaminan Keamanan Pangan:** Rentang masa simpan USDA FoodKeeper adalah panduan umum kualitas/keamanan; keputusan konsumsi tetap wajib memperhatikan kondisi fisik bahan (bau, warna, tekstur), suhu aktual penyimpanan, dan tanggal kedaluwarsa kemasan.
