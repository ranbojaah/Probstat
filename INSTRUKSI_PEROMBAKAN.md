# Instruksi Perombakan: Smart Food Inventory → Sistem Ketersediaan Bahan Baku (Supply Chain)

Dokumen ini adalah **spesifikasi kerja** untuk merombak aplikasi `smart_food_app` (Streamlit) yang ada (lihat `DOKUMENTASI.md`). Ikuti urutan dari atas ke bawah. Bagian 3 (hasil analisis data) memuat angka nyata dari dataset, bukan karangan, sehingga bisa dipakai sebagai nilai acuan dan sebagai kasus uji.

---

## 1. Tujuan Perombakan

Aplikasi lama menjawab: *"bahan yang sudah ada di gudang, mana yang harus dipakai dulu?"*
Aplikasi baru harus menjawab tiga pertanyaan tambahan, dengan **fokus pada ketersediaan bahan baku ayam dan daging**:

1. **Tahan berapa hari?** → sudah ada (FoodKeeper + modul `shelf_life.py`), dipertahankan.
2. **Kapan harus pesan ulang, dan berapa banyak?** → baru (peramalan permintaan, safety stock, reorder point).
3. **Stok maksimum berapa agar tidak busuk?** → baru (batas stok dari masa simpan).

Ukuran keberhasilan (KPI utama):

| KPI | Definisi | Target awal |
|---|---|---|
| **Tingkat layanan** (*cycle service level*) | % hari tanpa kehabisan stok | ≥ 95% |
| **Fill rate** | % permintaan yang terpenuhi dari stok | ≥ 98% |
| **Barang terbuang** | kg bahan melewati masa simpan | seminimal mungkin |
| **Rata-rata stok** | kg stok rata-rata di gudang | seminimal mungkin pada target layanan di atas |

Ini adalah *trade-off* inti: stok besar → layanan tinggi tetapi banyak busuk; stok kecil → sedikit busuk tetapi sering kehabisan. Aplikasi harus **menampilkan trade-off ini secara kuantitatif**.

### Ruang lingkup bahan (dua mode)

| Mode | Bahan | Sumber parameter permintaan | Label di aplikasi |
|---|---|---|---|
| **Data** | Ayam, lamb, steak, koefte (daging) | Dataset Mendeley (bagian 2.2) | "Berbasis data" |
| **Manual** | Semua bahan lain di FoodKeeper (sayur, susu, roti, seafood, dll) | **Diisi pengguna**: rata-rata pemakaian harian + variasi standar | "Berbasis asumsi pengguna" |

Fitur masa simpan, status, dan FEFO berlaku untuk **semua** bahan. Perencanaan pengadaan (ROP, safety stock, stok maksimum) berlaku untuk kedua mode, tetapi hasil mode manual **selalu dilabeli asumsi**.

---

## 2. Dataset yang Dipakai

### 2.1 USDA FoodKeeper (sudah ada) — untuk masa simpan
Tidak diubah. Parser `core/reference.py` tetap dipakai (kolom `DOP_*` diprioritaskan).

Pemetaan item restoran → produk FoodKeeper (ID dari sheet `Product`):

| Item di dataset permintaan | Produk FoodKeeper | ID | Kulkas (sejak beli) | Freezer |
|---|---|---:|---|---|
| `HAEHNCHEN` (ayam) | Chicken parts – legs or thighs | 118 | 1–2 hari | 9 bulan |
| `LAMM` (domba) | Lamb – chops, ribs, or loin | 51 | 3–5 hari | 4–12 bulan |
| `STEAK` (daging sapi) | Beef – steaks | 40 | 3–5 hari | 4–12 bulan |
| `KOEFTE` (bakso/daging giling) | Beef – ground | 43 | 1–2 hari | 3–4 bulan |

> Simpan pemetaan ini di `config.py` sebagai `ITEM_KE_PRODUK_ID`. Pemetaan harus bisa diubah pengguna di halaman Dataset.

### 2.2 Data permintaan harian (baru) — dari Mendeley Data
- **Sumber:** Taigel & Meller, *Data for: Machine learning for inventory management*, Mendeley Data, DOI `10.17632/7s3ys9ntnz.1`, lisensi **CC BY 4.0** (wajib mencantumkan sitasi di aplikasi dan laporan).
- **File asli:** `data_preprocessed.csv` (pemisah `;`, 760 baris × 293 kolom). Sebagian besar kolom adalah fitur turunan untuk machine learning dan **tidak dipakai**.
- **File bersih untuk aplikasi:** `permintaan_harian_restoran.csv` (sudah disiapkan, 760 baris × 7 kolom):

| Kolom | Arti |
|---|---|
| `tanggal` | `YYYY-MM-DD` (asli: format `bulan.hari.tahun`, mis. `10.4.2013` = 4 Okt 2013) |
| `ayam_porsi`, `lamm_porsi`, `steak_porsi`, `koefte_porsi` | jumlah porsi terjual per hari |
| `is_holiday`, `is_weekend` | penanda hari libur dan akhir pekan |

- **Cakupan:** 4 Okt 2013 – 7 Nov 2015 (760 hari), restoran di Stuttgart, Jerman. Tidak ada nilai kosong. Ada 3 celah tanggal (2 hari dan 4 hari) yang kemungkinan hari tutup; **jangan diisi dengan nilai karangan**, cukup dicatat.

### 2.3 Asumsi konversi porsi → kg (WAJIB ditulis di aplikasi dan laporan)
Dataset berisi **porsi**, bukan kg. Gunakan asumsi berikut (bisa diubah pengguna):

```python
GRAM_PER_PORSI = {"ayam": 200, "lamm": 200, "steak": 250, "koefte": 150}
```

Ini asumsi, bukan data. Semua angka kg di bawah mengikutinya. Beri label jelas: **"Konversi menggunakan asumsi gram per porsi"**.

### 2.4 Keterbatasan data yang harus dinyatakan terbuka di aplikasi
1. Data dari restoran **Jerman**, bukan Indonesia. Pola hari-dalam-minggu bisa dipakai sebagai contoh metodologi, tetapi **tidak ada efek Ramadan, Lebaran, atau Idul Adha**. Jika kasus studi kalian di Indonesia, sediakan tempat memasukkan **faktor event** manual (lihat 6.3).
2. Rentang data hanya ±2 tahun, sehingga setiap bulan hanya punya 2 pengamatan (Oktober 3). **Indeks musiman bulanan lemah**; yang kuat adalah pola hari-dalam-minggu.
3. Tidak ada data harga, lead time supplier, dan jumlah barang busuk. Semuanya harus diinput pengguna atau disimulasikan (dan dilabeli simulasi).

### 2.5 Mode input manual (untuk bahan tanpa data permintaan)
Dataset Mendeley hanya mencakup beberapa item, sedangkan FoodKeeper punya 661 produk. Untuk bahan lain, pengguna mengisi sendiri:

| Input | Contoh | Keterangan |
|---|---|---|
| `mean_kg_hari` | 4,0 | rata-rata pemakaian per hari (kg) |
| `cv` | 0,30 | koefisien variasi (variasi standar): $s = cv \times \text{mean}$ |
| `lead_time_hari` | 1 | dari tabel pemasok |

**Nilai default `cv = 0,30`.** Angka ini diturunkan dari data daging Mendeley: CV per hari-dalam-minggu berkisar **0,26–0,36 untuk ayam** dan **0,19–0,29 untuk daging**. Sediakan slider 0,10–0,60 dan tampilkan keterangan: *"Default dari variasi permintaan daging pada dataset restoran; ganti dengan nilai yang sesuai kondisi Anda."*

Aturan mode manual:
1. Tanpa riwayat, **tidak ada peramalan** dan **tidak ada indeks bulanan**. Perkiraan permintaan = `mean_kg_hari` yang datar (opsional dikali faktor event, 6.3).
2. Pola hari-dalam-minggu **tidak** dipakai kecuali pengguna mencentang "Pakai profil hari dari data daging". Jika dicentang, beri label "profil hari dipinjam dari dataset restoran (asumsi)".
3. Setiap tabel, grafik, dan ekspor yang memuat hasil mode manual wajib menampilkan lencana **"Asumsi pengguna"** dan tidak boleh disajikan sebagai hasil analisis data.
4. Jika pengguna kemudian mengunggah data permintaan untuk bahan itu, mode otomatis berpindah ke **Data**.

---

## 3. Hasil Analisis Dataset (acuan angka dan kasus uji)

Dihitung langsung dari `data_preprocessed.csv`. Hasil ini harus **dapat direproduksi** oleh kode aplikasi baru (jadikan unit test, lihat bagian 9).

### 3.1 Statistik deskriptif (porsi per hari)

| Item | Rata-rata | Simpangan baku | Min | Maks |
|---|---:|---:|---:|---:|
| Ayam | 30,40 | 11,95 | 0 | 93 |
| Lamb | 31,64 | 12,65 | 0 | 88 |
| Steak | 22,48 | 9,95 | 1 | 82 |
| Koefte | 22,09 | 9,27 | 2 | 71 |
| Daging total (lamb + steak + koefte) | 76,21 | 27,23 | – | – |

Uji normalitas Shapiro-Wilk: **tidak normal** untuk ayam (p ≈ 6,6×10⁻¹⁵) dan daging total (p ≈ 2,6×10⁻¹⁸). Konsekuensi: perhitungan safety stock berbasis z (normal) hanya pendekatan. Aplikasi **harus menyediakan juga versi kuantil empiris** dan menampilkan keduanya (lihat 6.2).

### 3.2 Pola hari dalam seminggu (sangat kuat)
Uji Kruskal-Wallis antar hari: ayam H ≈ 299,3 (p ≈ 1×10⁻⁶¹); daging H ≈ 378,8 (p ≈ 1×10⁻⁷⁸).

| Hari | Ayam (porsi) | Daging (porsi) |
|---|---:|---:|
| Senin | 24,0 | 62,1 |
| Selasa | 27,7 | 68,6 |
| Rabu | 30,2 | 73,4 |
| Kamis | 29,4 | 74,1 |
| Jumat | 33,8 | 87,7 |
| **Sabtu** | **46,6** | **115,7** |
| Minggu | 21,0 | 51,5 |

Sabtu ≈ 2,2× Minggu. **Inilah temuan terpenting:** satu angka safety stock untuk semua hari akan salah, tinggi di Minggu dan kurang di Sabtu. Parameter harus **per hari dalam minggu**.

### 3.3 Pola bulanan (lemah, perlu hati-hati)
Indeks musiman bulanan (rasio terhadap rata-rata hari yang sama, setelah koreksi hari-dalam-minggu):

| Bulan | Jan | Feb | Mar | Apr | Mei | Jun | Jul | Agu | Sep | Okt | Nov | Des |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ayam | 0,99 | 0,98 | 1,05 | 0,96 | 0,95 | 0,95 | 0,97 | 0,96 | 0,95 | 1,08 | **1,13** | 1,00 |
| Daging | 1,03 | 0,99 | 1,04 | 0,93 | 1,02 | 0,93 | 0,94 | 0,98 | 0,93 | 1,04 | **1,10** | 1,04 |

Kruskal-Wallis efek bulan pada rasio hasil koreksi hari: ayam p ≈ 0,0004, daging p ≈ 1,5×10⁻⁶ (signifikan secara statistik), tetapi besarnya hanya ±5–13% dan **hanya 2 tahun data**. Perlakukan sebagai **indikatif**, bukan pasti.

### 3.4 Parameter pengadaan dalam kg (asumsi gram per porsi di 2.3; z = 1,645; lead time L = 1 hari)

**Ayam (kg):**

| Hari | Mean | Std | Safety stock | ROP |
|---|---:|---:|---:|---:|
| Senin | 4,8 | 1,6 | 2,7 | 7,5 |
| Selasa | 5,5 | 1,5 | 2,5 | 8,1 |
| Rabu | 6,0 | 2,0 | 3,3 | 9,3 |
| Kamis | 5,9 | 1,6 | 2,6 | 8,5 |
| Jumat | 6,8 | 2,0 | 3,2 | 10,0 |
| Sabtu | 9,3 | 2,4 | 4,0 | 13,3 |
| Minggu | 4,2 | 1,5 | 2,5 | 6,7 |

**Daging total (kg):**

| Hari | Mean | Std | Safety stock | ROP |
|---|---:|---:|---:|---:|
| Senin | 12,4 | 3,6 | 6,0 | 18,4 |
| Selasa | 13,7 | 3,1 | 5,2 | 18,9 |
| Rabu | 14,7 | 3,0 | 4,9 | 19,6 |
| Kamis | 14,8 | 2,8 | 4,7 | 19,4 |
| Jumat | 17,5 | 4,2 | 6,9 | 24,4 |
| Sabtu | 23,3 | 6,5 | 10,6 | 33,9 |
| Minggu | 10,4 | 2,8 | 4,6 | 15,0 |

Rata-rata keseluruhan: ayam **6,08 kg/hari**, daging **15,26 kg/hari**.
Cek empiris: dengan ROP per hari di atas, permintaan harian tercakup pada **94,6% hari (ayam)** dan **94,2% hari (daging)** (in-sample), mendekati target 95%.

### 3.5 Kebutuhan per bulan (contoh dari indeks 3.3, 30 hari)

| | Bulan biasa | November (indeks naik) |
|---|---:|---:|
| Ayam | ≈ 182 kg | ≈ 206 kg |
| Daging | ≈ 458 kg | ≈ 505 kg |

### 3.6 Batas stok dari masa simpan
Dengan masa simpan konservatif (ambil batas bawah FoodKeeper): ayam **1 hari**, koefte **1 hari**, lamb dan steak **3 hari**. Contoh ayam di hari Sabtu: ROP 13,3 kg, tetapi stok segar maksimum yang aman hanya setara kebutuhan ±1–2 hari (≈ 9–14 kg). Artinya **tidak ada ruang untuk menimbun ayam segar**; pasokan harus sering (harian), dan cadangan untuk lonjakan hanya masuk akal lewat freezer (ayam 9 bulan).

---

## 4. Ringkasan Perubahan terhadap Aplikasi Lama

| Komponen | Tindakan |
|---|---|
| `core/reference.py`, `core/shelf_life.py` (masa simpan, probabilitas Seragam) | **Pertahankan.** Tambah fungsi batas stok dan *expected waste* (6.4) |
| FIFO (`urutan_fifo`) | **Ganti jadi FEFO** (*First-Expired, First-Out*), urut berdasarkan `sisa efektif` terkecil |
| `core/stats.py` (Shapiro, Kruskal-Wallis, Wilson) | **Pertahankan dan arahkan** ke data permintaan (uji hari, uji bulan, CI Wilson untuk % hari kehabisan stok) |
| Kaplan-Meier, Log-Rank, Cox | **Turunkan prioritas.** Sembunyikan kecuali data historis pembusukan tersedia. Jangan dihapus |
| Halaman Dashboard, Inventaris, Dataset, Laporan | **Ubah isi** (bagian 7) |
| Perencanaan pengadaan, peramalan, simulasi, pemasok | **Baru** |
| Bahan di luar ayam dan daging | **Mode manual** (2.5): pengguna input rata-rata dan CV |
| `database/db.py` | **Tambah tabel** (bagian 5) |

---

## 5. Skema Database Baru (SQLite, tambahkan di `db.init_db()`)

```sql
-- Permintaan/pemakaian harian per item (hasil impor dataset atau input harian)
CREATE TABLE IF NOT EXISTS permintaan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal TEXT NOT NULL,            -- YYYY-MM-DD
  item TEXT NOT NULL,               -- ayam | lamm | steak | koefte (atau bahan lain)
  jumlah_porsi REAL NOT NULL,
  sumber TEXT DEFAULT 'impor',      -- impor | manual | simulasi
  UNIQUE(tanggal, item)
);

-- Master pemasok
CREATE TABLE IF NOT EXISTS pemasok (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  lead_time_rata REAL NOT NULL,     -- hari
  lead_time_std REAL DEFAULT 0,     -- hari
  keandalan REAL DEFAULT 1.0        -- 0..1, proporsi pengiriman tepat waktu
);

-- Bahan yang dipasok pemasok
CREATE TABLE IF NOT EXISTS pemasok_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pemasok_id INTEGER NOT NULL REFERENCES pemasok(id),
  item TEXT NOT NULL,
  harga_per_kg REAL,
  moq_kg REAL DEFAULT 0             -- minimum order
);

-- Parameter per item (hasil konfigurasi pengguna)
CREATE TABLE IF NOT EXISTS parameter_item (
  item TEXT PRIMARY KEY,
  produk_id INTEGER,                -- pemetaan ke FoodKeeper
  gram_per_porsi REAL NOT NULL,
  tingkat_layanan REAL DEFAULT 0.95,
  biaya_kurang_per_kg REAL,         -- Cu: biaya kehabisan stok
  biaya_lebih_per_kg REAL,          -- Co: biaya barang busuk
  mode_permintaan TEXT DEFAULT 'manual',  -- data | manual
  mean_manual_kg_hari REAL,         -- hanya mode manual
  cv_manual REAL DEFAULT 0.30,      -- hanya mode manual
  pakai_profil_hari INTEGER DEFAULT 0     -- 1 = pinjam profil hari dari data daging
);

-- Pesanan pembelian
CREATE TABLE IF NOT EXISTS pesanan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal_pesan TEXT NOT NULL,
  tanggal_datang_estimasi TEXT,
  pemasok_id INTEGER REFERENCES pemasok(id),
  item TEXT NOT NULL,
  jumlah_kg REAL NOT NULL,
  status TEXT DEFAULT 'dipesan'     -- dipesan | diterima | batal
);
```

Tabel `inventaris` lama dipakai apa adanya (satu baris = satu *batch* dengan `tanggal_diterima`). Tambahkan kolom `item` (kunci ke `parameter_item`) agar batch bisa dikaitkan ke permintaan.

---

## 6. Modul Logika Baru (`core/`, tanpa ketergantungan Streamlit)

### 6.1 `core/permintaan.py` — muat dan siapkan data
- `muat_permintaan(file_or_path)`: baca CSV (`;` atau `,` otomatis), parse tanggal, validasi kolom.
- `ke_kg(df, gram_per_porsi)`: tambah kolom `*_kg = porsi × gram / 1000`; tambah kolom `daging_kg = lamm + steak + koefte`.
- `laporan_kualitas(df)`: jumlah hari, rentang tanggal, celah tanggal, nilai nol, outlier (aturan IQR). **Jangan imputasi**; tampilkan saja.
- Fitur kalender: `hari` (0–6), `bulan`, `is_weekend`, `is_holiday`.

### 6.2 `core/procurement.py` — inti perencanaan

Semua fungsi menerima parameter **per hari dalam minggu** (bukan satu angka tunggal).

```python
def parameter_per_hari(df_kg, kolom):
    """Return DataFrame index=hari(0..6): mean, std, q95_empiris, n."""

def parameter_manual(mean_kg_hari, cv=0.30, profil_hari=None):
    """Mode manual. std = cv * mean.
    Tanpa profil_hari: mean dan std sama untuk semua hari.
    Dengan profil_hari (rasio 7 nilai, rata-rata = 1): mean_h = mean * rasio_h.
    Return DataFrame yang bentuknya sama dengan parameter_per_hari,
    kolom tambahan sumber='asumsi' (dipakai UI untuk lencana)."""

def safety_stock(std, L_hari, z=1.645, std_L=0.0, mean_d=0.0):
    # Versi dasar:   SS = z * std * sqrt(L)
    # Jika lead time bervariasi:
    #   SS = z * sqrt(L * std**2 + (mean_d**2) * std_L**2)
    ...

def safety_stock_empiris(residual_rasio, mean_d, L_hari, tingkat_layanan=0.95):
    # Pakai kuantil empiris dari rasio permintaan/rata-rata-hari, bukan asumsi normal.
    ...

def reorder_point(mean_d, L_hari, ss):   # ROP = mean_d * L + SS
    ...

def order_up_to(forecast_hari_ke_depan, L_hari, R_hari, std, z):
    # S = sum(forecast selama L+R hari) + z*std*sqrt(L+R)
    ...

def stok_maks_masa_simpan(forecast_harian, masa_simpan_hari):
    # Batas tertinggi agar tidak busuk = jumlah forecast selama masa_simpan hari ke depan.
    ...

def kuantitas_pesan(stok_sekarang, pesanan_dalam_perjalanan, S, S_cap, moq=0):
    # q = max(0, min(S, S_cap) - stok_sekarang - pesanan_dalam_perjalanan); bulatkan ke MOQ
    ...

def newsvendor(forecast_mean, forecast_std, Cu, Co):
    # CR = Cu/(Cu+Co); Q* = mean + z(CR)*std   (barang perishable, satu periode)
    ...
```

Aturan keputusan (kebijakan *periodic review*, R = 1 hari, cocok untuk ayam dan daging segar):

1. Hitung `S` (target stok) dan `S_cap` (batas masa simpan).
2. Jika `S ≤ S_cap`: pesan sampai `S`.
3. Jika `S > S_cap`: pesan sampai `S_cap` **dan tampilkan peringatan**: "target layanan tidak tercapai tanpa risiko busuk; tingkat layanan efektif ≈ X%" (hitung X dari `S_cap`). Tawarkan solusi: pesan lebih sering (kurangi L+R), tambah cadangan freezer, atau terima layanan lebih rendah.

### 6.3 `core/forecast.py` — peramalan
Sediakan tiga metode, dievaluasi dengan **rolling-origin** (latih pada data awal, uji pada hari berikutnya, geser maju):

| Metode | Deskripsi |
|---|---|
| Naif musiman | rata-rata hari yang sama pada 4 minggu terakhir |
| Rata-rata hari × indeks bulan | mean per hari-dalam-minggu × indeks bulanan (3.3) |
| Holt-Winters | `statsmodels.tsa.holtwinters.ExponentialSmoothing`, `seasonal_periods=7`, `trend=None` |

- Metrik: **MAE, RMSE, sMAPE** (hindari MAPE biasa karena ada hari bernilai 0).
- Pilih metode dengan RMSE terendah sebagai default, tetapi biarkan pengguna mengganti.
- Interval prediksi dari kuantil residual rolling-origin.
- **Faktor event manual:** tabel kecil `(tanggal_mulai, tanggal_selesai, faktor, keterangan)` untuk Ramadan, Lebaran, dll. Forecast akhir = forecast dasar × faktor event. Tandai kolom hasil sebagai "dipengaruhi asumsi event".
- **Mode manual:** lewati perbandingan metode. `forecast_harian` = `mean_kg_hari` (datar) × faktor event bila ada. Interval prediksi dari $\pm z \cdot cv \cdot \text{mean}$.

### 6.4 Tambahan di `core/shelf_life.py`
- `fefo_urutan(batch_df)`: urut berdasarkan `sisa efektif` terkecil, lalu tanggal diterima.
- `expected_waste(batch_df, forecast_harian)`: simulasikan konsumsi FEFO terhadap forecast; kg batch yang kemungkinan melewati batas = estimasi barang busuk. Pakai `P(lewat batas)` dari model Seragam yang sudah ada.

### 6.5 `core/simulasi.py` — Monte Carlo dan backtest
Bandingkan kebijakan pada data nyata (backtest) maupun permintaan bootstrap:

| Kebijakan | Aturan |
|---|---|
| A. Naif | pesan sebesar rata-rata permintaan harian |
| B. ROP + safety stock | 6.2 tanpa batas masa simpan |
| C. ROP + safety stock + batas masa simpan | 6.2 lengkap (usulan) |

Simulasi harian: permintaan terjadi → dipenuhi dari stok FEFO → barang melewati masa simpan dibuang → pesanan tiba setelah lead time (acak sesuai `lead_time_rata`, `lead_time_std`). Keluaran: **% hari kehabisan stok, fill rate, kg terbuang, rata-rata stok, total biaya**. Gunakan seed tetap agar hasil reproducible dan minimal 1.000 replikasi; beri interval kepercayaan (CI Wilson untuk % kehabisan stok). Untuk bahan **mode manual**, bangkitkan permintaan dari distribusi Normal terpotong di 0 (atau Gamma) dengan mean dan CV yang diinput, dan labeli hasilnya **simulasi berbasis asumsi**.

---

## 7. Halaman Aplikasi (`views/`)

Urutan navigasi baru (daftarkan di `nav.py`):

1. **Dashboard Ketersediaan** (ubah `dashboard.py`)
   - KPI: bahan di bawah ROP, bahan berisiko kehabisan 1–3 hari, bahan Kritis (masa simpan), perkiraan barang busuk, tingkat layanan.
   - Tabel "Perlu dipesan hari ini": item, stok sekarang, ROP, jumlah pesan yang disarankan (kg), pemasok.
   - Grafik stok vs ROP vs batas maksimum per item.
2. **Inventaris Bahan** (ubah `inventaris.py`)
   - Pertahankan CRUD dan aksi Habis/Busuk. Tambah kolom `item`, urutan **FEFO**, dan tombol "Terima pesanan" yang menambah batch dari tabel `pesanan`.
3. **Permintaan & Peramalan** (baru, `permintaan.py`)
   - Unggah dataset, laporan kualitas, pengaturan gram per porsi.
   - Grafik permintaan harian, rata-rata per hari-dalam-minggu (dengan CI), indeks bulanan (beri catatan "data hanya ±2 tahun").
   - Hasil uji Shapiro, Kruskal-Wallis hari dan bulan.
   - Perbandingan metode forecast (MAE, RMSE, sMAPE) dan grafik ramalan 14 hari dengan interval.
4. **Perencanaan Pengadaan** (baru, `pengadaan.py`) — **halaman inti**
   - Input: tingkat layanan, lead time, masa simpan (otomatis dari FoodKeeper).
   - Pilih bahan dari seluruh daftar FoodKeeper. Jika bahan **punya data** → mode Data. Jika **tidak** → tampilkan formulir mode manual (rata-rata kg/hari, CV, centang profil hari) dan lencana **"Asumsi pengguna"** di setiap hasil.
   - Tabel per item per hari: Mean, Std, Safety Stock (z dan empiris, berdampingan), ROP, Stok Maks, Jumlah Pesan.
   - Panel "Kalender restok bulanan": kebutuhan kg per bulan (3.5) dengan indeks musiman dan faktor event.
   - Peringatan jika `S > S_cap` (6.2 poin 3).
   - Expander rumus LaTeX + substitusi angka (seperti gaya halaman lama).
5. **Simulasi & Evaluasi** (baru, `simulasi.py`)
   - Bandingkan kebijakan A/B/C (6.5) dengan tabel dan grafik trade-off layanan vs barang terbuang.
   - Slider tingkat layanan dan lead time; tampilkan titik terbaik.
6. **Pemasok** (baru, `pemasok.py`)
   - CRUD pemasok, lead time rata-rata dan simpangan baku, keandalan, harga, MOQ.
7. **Dataset** (ubah `dataset.py`)
   - Tab Permintaan (unggah, pemetaan kolom, sitasi Mendeley), tab Referensi FoodKeeper (tetap), tab Pemetaan item→produk FoodKeeper, tab **Parameter Bahan** (daftar bahan, mode Data/Manual, mean dan CV manual, gram per porsi).
8. **Laporan** (ubah `laporan.py`)
   - Ekspor CSV rencana pengadaan dan PDF ringkasan (parameter, asumsi, hasil simulasi, sitasi dataset).

Semua halaman wajib menampilkan **kotak asumsi** (gram per porsi, sumber data, keterbatasan 2.4) agar pembaca tidak salah mengira angka simulasi/asumsi sebagai data asli.

---

## 8. Rumus yang Harus Tampil di Aplikasi (LaTeX + substitusi angka)

- Rata-rata dan simpangan baku permintaan per hari: $\bar{d}_h$, $s_h$
- Safety stock (normal): $SS = z\,s_h\sqrt{L}$, dengan $z = \Phi^{-1}(\text{tingkat layanan})$
- Safety stock (lead time acak): $SS = z\sqrt{L\,s_h^2 + \bar{d}_h^2\,s_L^2}$
- Reorder point: $ROP = \bar{d}_h L + SS$
- Target stok periodic review: $S = \sum_{t=1}^{L+R}\hat{d}_t + z\,s_h\sqrt{L+R}$
- Batas masa simpan: $S_{cap} = \sum_{t=1}^{m}\hat{d}_t$, $m$ = masa simpan konservatif (hari)
- Jumlah pesan: $q = \max\bigl(0,\ \min(S, S_{cap}) - I - I_{pipeline}\bigr)$
- Newsvendor: $CR = \dfrac{C_u}{C_u + C_o}$, $Q^{*} = \bar{d} + z_{CR}\,s$
- Indeks musiman: $I_m = \dfrac{\text{rata-rata rasio bulan } m}{\text{rata-rata keseluruhan}}$
- Uji Kruskal-Wallis (hari, bulan) dan CI Wilson untuk proporsi hari kehabisan stok (rumus sudah ada di dokumentasi lama)

---

## 9. Pengujian (`tests/`)

Tambahkan unit test yang **harus lulus** (angka dari bagian 3, toleransi ±0,05 kecuali dinyatakan lain):

1. `muat_permintaan`: 760 baris; tanggal pertama 2013-10-04, terakhir 2015-11-07; tanpa nilai kosong.
2. Format tanggal `10.4.2013` terbaca sebagai **4 Oktober 2013** (bukan 10 April).
3. Rata-rata ayam = 30,40 porsi/hari; simpangan baku = 11,95.
4. Rata-rata ayam hari Sabtu ≈ 46,55 porsi; Minggu ≈ 21,00.
5. Dengan 200 g/porsi: rata-rata ayam = 6,08 kg/hari; ROP Sabtu (L=1, z=1,645) ≈ 13,3 kg.
6. `safety_stock` naik jika lead time naik dan jika tingkat layanan naik (uji monoton).
7. `kuantitas_pesan` tidak pernah negatif dan tidak melebihi `S_cap − stok`.
8. Backtest kebijakan C: persentase hari kehabisan stok ≤ 8% pada target 95% (data in-sample).
9. Seed simulasi sama → hasil sama persis.
10. Semua tes lama di `tests/test_core.py` tetap lulus.
11. Mode manual: `mean=10 kg/hari`, `cv=0,30`, `L=1`, `z=1,645` → `std=3,0`, `SS≈4,94 kg`, `ROP≈14,94 kg`.
12. Mode manual dengan `cv` lebih besar menghasilkan `SS` lebih besar (uji monoton); `mean=0` tidak menyebabkan error.
13. Setiap hasil mode manual membawa penanda `sumber='asumsi'`; hasil mode Data membawa `sumber='data'`.
14. Mengunggah data permintaan untuk bahan bermode manual memindahkannya ke mode Data.

Tambahkan juga **uji sanity**: jika masa simpan lebih pendek dari `L+R`, aplikasi harus menampilkan peringatan, bukan error.

---

## 10. Urutan Pengerjaan yang Disarankan

1. **Data:** tambahkan tabel DB (bagian 5), `core/permintaan.py`, halaman Dataset (tab Permintaan), impor `permintaan_harian_restoran.csv`. Verifikasi tes 1–4.
2. **Statistik permintaan:** halaman Permintaan & Peramalan bagian deskriptif (grafik, Shapiro, Kruskal-Wallis, indeks).
3. **Inti pengadaan:** `core/procurement.py` + halaman Perencanaan Pengadaan. Verifikasi tes 5–7.
4. **Peramalan:** `core/forecast.py` + perbandingan metode.
5. **Simulasi:** `core/simulasi.py` + halaman Simulasi. Verifikasi tes 8–9.
6. **FEFO dan inventaris:** ubah urutan, tambah `item`, tombol terima pesanan, `expected_waste`.
7. **Pemasok, Dashboard, Laporan.**
8. **Dokumentasi:** perbarui `DOKUMENTASI.md` (bagian 8 "Batasan" harus ditulis ulang karena ruang lingkup supply chain kini sebagian tercakup) dan `README.md`, cantumkan sitasi Mendeley dan USDA.

---

## 11. Catatan Penting untuk Laporan/Presentasi

- Sebutkan jelas bahwa data permintaan berasal dari **restoran Jerman (2013–2015)** dan dipakai untuk mendemonstrasikan metode; angka rupiah, lead time, dan harga bersifat **asumsi** kecuali kalian mengumpulkan data sendiri.
- Panduan masa simpan FoodKeeper adalah **panduan umum**, bukan jaminan keamanan pangan; selalu konfirmasi dengan kondisi fisik bahan dan suhu kulkas.
- Untuk bahan **mode manual**, jelaskan bahwa mean dan CV adalah asumsi pengguna (CV default 0,30 diturunkan dari variasi daging pada dataset restoran), sehingga hasilnya bersifat ilustrasi perencanaan, bukan analisis data.
- Jika nanti tersedia data pemakaian asli dari tempat studi kasus di Indonesia, ganti file permintaan tanpa mengubah kode; semua parameter (bagian 3.4) akan terhitung ulang otomatis.
- Sitasi dataset: Taigel, F., & Meller, J. (2020). *Data for: Machine learning for inventory management: Analyzing two concepts to get from data to decisions*. Mendeley Data, V1. https://doi.org/10.17632/7s3ys9ntnz.1 (CC BY 4.0).
