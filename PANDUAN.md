# Nero — Panduan Singkat

Nero adalah aplikasi pribadi berisi kumpulan alat untuk membantu menghasilkan uang dari internet. Semua berjalan di komputer Anda sendiri; data dan hasilnya tidak dikirim ke mana pun (kecuali ke Claude bila Anda mengisi API key).

Fitur yang tersedia sekarang:

| Fitur | Kegunaan |
|---|---|
| **Clip Maker** | Ubah video panjang (dari link atau file) menjadi video pendek vertikal 9:16 siap upload ke TikTok, Instagram Reels, dan YouTube Shorts. |

Fitur lain akan ditambahkan di versi berikutnya dan otomatis muncul di menu.

## Instalasi (sekali saja)

1. Ekstrak folder `Nero` ke tempat yang mudah, misalnya `D:\Nero`.
2. Klik dua kali **install.bat**. Ia akan menginstal Python, FFmpeg, Deno (dibutuhkan untuk unduhan YouTube), paket yang diperlukan, dan model transkrip (sekitar 500 MB). Bila komputer punya kartu grafis NVIDIA, pustaka CUDA (sekitar 1 GB) ikut dipasang supaya transkrip jauh lebih cepat.
   - Jika muncul pesan "Python selesai diinstal", tutup jendelanya lalu jalankan **install.bat** sekali lagi.
3. Selesai. Butuh koneksi internet dan ruang disk kurang lebih 3 GB.

## Memakai Nero

1. Klik dua kali **run.bat**. Browser akan terbuka di `http://127.0.0.1:7860`. Biarkan jendela hitam tetap terbuka selama memakai aplikasi.
2. Halaman pertama adalah **Beranda**: ringkasan semua fitur (berapa tugas sedang berjalan, berapa hasil yang sudah jadi). Pilih fitur dari kartu di Beranda atau dari menu di kiri (di layar kecil: menu di atas).
3. Di bawah menu ada:
   - **Folder hasil**: membuka folder `output`. Setiap fitur punya subfoldernya sendiri, mis. `output\clip`.
   - **Pengaturan**: pengaturan umum yang dipakai semua fitur (Claude API key, model AI, cookies browser).
   - Tanda **Terhubung** / **Terputus** (bila terputus, jendela run.bat tertutup) dan apakah **AI Claude** aktif.

### Pindah dari ClipMaker versi lama

Cukup timpa berkas aplikasinya (folder `data` dan `output` jangan dihapus). Saat pertama dibuka, Nero otomatis memindahkan proyek lama ke `data\clip\projects` dan hasil render lama ke `output\clip`; pengaturan dan API key tetap terbawa. Bila ada berkas yang sedang dibuka program lain, berkas itu dilewati dan dipindah saat Nero dibuka berikutnya (jendela run.bat memberi tahu).

Folder aplikasi boleh diganti namanya (mis. `ClipMaker` menjadi `Nero`); tidak perlu instal ulang.

## Clip Maker

Buka **Clip Maker** dari menu.

1. **Masukkan video**: tempel satu atau banyak link (satu per baris), atau tarik file video dari komputer. Tentukan jumlah clip dan **bahasa** yang diucapkan di video, lalu tekan **Proses**.
2. Aplikasi akan mengunduh, membuat transkrip, dan mencari momen paling menarik. Setiap momen diberi **skor** dan **alasan**. Proses yang sedang berjalan bisa dihentikan dengan **✕ Batal**.
3. Periksa daftar clip:
   - Ubah judul/hook (teks yang tampil di atas video).
   - Geser waktu mulai/selesai, atau pakai tombol −1 / +1 detik.
   - **Pratinjau** untuk menonton bagian aslinya.
   - **Transkrip** untuk memilih kalimat sendiri lalu menjadikannya clip.
   - **Subtitle** untuk mengoreksi kata yang salah dengar (nama orang, istilah, bahasa gaul). Waktu tiap kata tetap dipakai, jadi sebaiknya hanya mengganti kata, jangan menambah/menghapus banyak. Koreksi tersimpan di transkrip proyek, jadi ikut berlaku untuk clip lain di bagian yang sama. Clip yang sudah dirender diberi tanda **Subtitle diubah, render ulang**.
   - Hapus centang clip yang tidak ingin dirender.
4. Atur **Gaya video** (berlaku untuk semua render berikutnya). Tekan **👁 Pratinjau gaya** untuk melihat hasilnya di satu frame tanpa menunggu render. Lalu tekan **Render**. Analisis video lain tetap bisa berjalan bersamaan dengan render. Pilihan gaya subtitle:
   - **Font**: Impact, Montserrat ExtraBold, Anton, Bebas Neue, Poppins ExtraBold, atau Arial Black. Juga dipakai untuk judul.
   - **Warna teks** (warna dasar subtitle) dan **Warna sorotan kata** (kata yang sedang diucapkan).
   - **Sorot kata kunci**: angka dan kata pemancing perhatian (rahasia, ternyata, juta, gagal, dll.) selalu berwarna sorotan dan sedikit lebih besar.
   - **Hapus jeda**: diam lebih dari 0,3 atau 0,6 detik dibuang otomatis supaya tempo lebih rapat. Audio tetap sinkron, dan file `.srt` ikut menyesuaikan.
5. Hasil muncul di daftar dan tersimpan di folder `output\clip` (tombol **Folder hasil** di atas halaman Clip Maker). Untuk setiap clip ada:
   - `.mp4` video 1080×1920 siap upload
   - `.srt` subtitle terpisah
   - `_caption.txt` caption postingan + hashtag (tombol **Caption** juga menyalinnya)

Centang **Langsung render otomatis** bila ingin semua momen langsung dijadikan video tanpa diperiksa dulu.

**Pengaturan clip** (tombol di atas halaman Clip Maker) berisi model transkrip, bahasa video bawaan, jumlah clip bawaan, dan durasi minimum/maksimum clip.

### Referensi & instruksi (timeline riset, clip contoh, prompt)

Klik **Referensi & instruksi** di kartu "Masukkan video" (atau **Cari ulang + referensi** pada proyek yang sudah ada) untuk mengarahkan hasil. Tulis satu referensi per baris:

```
12:30 - 13:45 Kenapa bisnis pertamaku bangkrut?
1:02:10 - 1:03:00 tips mengatur uang
45:20 momen lucu
https://www.tiktok.com/@akun/video/...
https://youtu.be/IDVIDEO?t=754
Fokus pada momen tentang "investasi". Judul berupa pertanyaan. Jangan ambil bagian sponsor.
```

| Baris | Hasilnya |
|---|---|
| `mm:ss - mm:ss` atau `j:mm:ss - j:mm:ss` (boleh `12.30 - 13.45`, `s/d`, `sampai`) | **Timeline riset**: pasti dijadikan clip dengan waktu itu (dirapikan ke awal/akhir kalimat bila selisihnya ≤ 2 detik). Teks setelah waktu menjadi judul (mode lokal) atau catatan untuk AI. |
| `mm:ss catatan` | **Titik waktu**: dibuatkan clip yang dimulai sedikit sebelum titik itu. |
| Link clip pendek orang lain (TikTok/Reels/Shorts) | **Clip referensi**: audionya diunduh dan ditranskrip, lalu dicari bagian yang sama di video Anda. Bila ketemu, bagian itu dijadikan clip. Bila tidak ada (clip dari video lain), dipakai sebagai contoh gaya/topik. Maksimal 5 link, masing-masing maks 15 menit. |
| Link YouTube video ini dengan `?t=` | Dianggap titik waktu. |
| Teks lain | **Instruksi/prompt**. Dengan Claude API key, instruksi dibaca AI apa adanya (topik, gaya judul, bahasa caption, dll). Tanpa API key, kata-katanya dipakai sebagai kata kunci topik: `"frasa dalam kutip"` dicocokkan utuh, dan kata setelah *jangan/hindari/tanpa* diberi skor minus. |

Link di kolom ini hanya menentukan **momen** yang dipotong, bukan tampilan editannya. Untuk meniru tampilan, lihat bagian berikut.

Di bawah kolom muncul daftar **Dikenali** supaya Anda bisa memastikan setiap baris terbaca dengan benar. **Jumlah clip** adalah total: timeline dan titik Anda selalu masuk, sisanya diisi momen pilihan otomatis. Bila hanya ingin clip dari riset Anda, isi Jumlah clip sama dengan banyaknya timeline. Clip dari referensi diberi tanda **Timeline Anda**, **Titik riset Anda**, atau **Sama dengan clip referensi**.

### Tiru gaya dari clip referensi (tanpa API key)

Di kartu **2. Gaya video**, tempel link clip yang gaya editannya ingin ditiru (TikTok/Reels/Shorts) lalu tekan **Baca gaya**, atau pilih file video dengan tombol **File**. Aplikasi membaca 40 detik pertama clip itu di komputer Anda dan menebak:

- **Subtitle**: posisi, ukuran, jumlah kata per tampilan, HURUF BESAR atau tidak, warna teks dan warna sorotan kata
- **Judul/hook**: ada atau tidak, warna kotaknya (putih/kuning/hitam), tampil sepanjang video atau hanya 3/5 detik pertama
- **Progress bar** di bawah
- **Tata letak**: ikuti wajah, dua orang (atas/bawah), video utuh + latar blur, atau potong tengah

Hasilnya ditampilkan dulu: nilai yang berbeda dari pengaturan sekarang dicetak tebal. Tekan **Pratinjau dulu** untuk melihat satu frame, lalu **Terapkan gaya ini** bila cocok. Bagian yang tidak terbaca dengan yakin tidak diubah.

Batasannya: hanya untuk video vertikal 9:16, dan paling akurat untuk subtitle ber-outline hitam (gaya TikTok umumnya). Jenis font, animasi teks, zoom, musik, b-roll, dan watermark tidak bisa ditiru. Ukuran subtitle dikalibrasi untuk font Impact; dengan font lain bisa meleset sekitar 15%. HURUF BESAR/kecil hanya diubah bila terbaca pasti; subtitle Impact huruf kecil satu kata per tampilan bisa terbaca sebagai HURUF BESAR. Bila video aslinya sendiri banyak tulisan (slide, berita), hasil subtitle/judul bisa keliru, jadi periksa pratinjaunya sebelum menerapkan.

Setelah semua clip selesai, tekan **🧹 Hapus video sumber** untuk menghemat disk (video asli bisa ratusan MB). Hasil render tetap aman, tetapi clip proyek itu tidak bisa dirender ulang.

### Kemampuan Clip Maker

- Deteksi momen menarik otomatis (hook kalimat pembuka, pertanyaan, kata kunci emosional, energi suara, kepadatan bicara)
- Subtitle otomatis gaya TikTok: 1–4 kata per tampilan, kata yang diucapkan disorot warna, efek muncul
- Crop pintar 9:16 mengikuti wajah pembicara dengan gerakan kamera halus
- Tata letak **Dua orang (atas/bawah)** untuk podcast/wawancara: tiap orang mendapat setengah layar (dipilih otomatis bila terdeteksi dua wajah berdampingan)
- Tata letak alternatif: video utuh dengan latar blur, atau potong tengah
- Transkrip di GPU NVIDIA bila tersedia (otomatis kembali ke CPU bila gagal); encode video juga memakai GPU (NVENC) bila bisa
- Render cepat: beberapa frame disusun bersamaan (clip 14 detik ±6 detik di laptop RTX 3050)
- Judul/hook di atas video, progress bar, watermark @akun
- Volume suara diratakan sesuai standar media sosial
- Proses banyak link sekaligus dengan antrian
- Caption + hashtag siap salin

## Mode AI (opsional, lebih pintar)

Tanpa pengaturan apa pun, setiap fitur bekerja dengan algoritma lokal (gratis); di Clip Maker, momen dipilih otomatis di komputer Anda. Untuk hasil yang jauh lebih bagus (di Clip Maker: pemilihan momen, judul hook, dan caption), isi **Claude API key** di **Pengaturan** (menu kiri bawah). Kunci ini dipakai bersama oleh semua fitur. Kunci bisa dibuat di https://console.anthropic.com (berbayar per pemakaian; satu video biasanya hanya beberapa sen dolar). Kunci hanya disimpan di komputer Anda (`data/settings.json`).

## Tips & masalah umum

| Masalah | Solusi |
|---|---|
| Unduhan YouTube gagal / "confirm you're not a bot" | Di **Pengaturan** (menu kiri bawah), isi "Ambil cookies dari browser" dengan browser tempat Anda login YouTube (chrome/edge/firefox). Tutup browser itu saat mengunduh. |
| Unduhan tiba-tiba gagal padahal dulu bisa | Jalankan **update.bat** (situs video sering berubah). |
| Transkrip lambat | Lihat baris di bawah tombol Proses: bila tertulis "memakai CPU" padahal ada kartu NVIDIA, jalankan **install.bat** lagi. Atau di **Pengaturan clip** ganti model transkrip ke **base**. Dengan GPU, pakai **large-v3-turbo**: hampir seakurat large-v3 tetapi jauh lebih cepat. |
| Subtitle kurang tepat / malah diterjemahkan | Pastikan pilihan **Bahasa** saat menambahkan video sesuai bahasa yang diucapkan (atau pilih Deteksi otomatis), dan pakai model **medium**. |
| Wajah tidak diikuti | Pilih tata letak **Ikuti wajah**, **Dua orang (atas/bawah)** untuk podcast, atau **Video utuh + latar blur** untuk video dengan banyak orang. |

Gunakan aplikasi ini untuk video milik Anda sendiri atau yang Anda punya izin untuk mengunggah ulang.

## Struktur folder

```
Nero/
  install.bat, run.bat, update.bat
  requirements*.txt daftar paket (lock = versi yang sudah teruji, gpu = pustaka CUDA)
  app.py            server web lokal: keamanan, tampilan, pengaturan umum, memuat semua fitur
  common.py         bagian bersama semua fitur (lokasi folder, pengaturan, hapus berkas)
  features/         satu folder per fitur
    clip/           Clip Maker: api.py (rute & antrian), engine.py (unduh, transkrip, momen, render)
  web/              tampilan aplikasi siap pakai (hasil build frontend/, jangan diubah langsung)
  frontend/         kode sumber tampilan: Next.js + TypeScript + Tailwind CSS + shadcn/ui
  models/           model deteksi wajah
  fonts/            font subtitle gratis (lisensi SIL OFL, berkas OFL-*.txt)
  tests/            tes otomatis
  output/           HASIL ANDA, satu subfolder per fitur (output/clip = video clip)
  data/             pengaturan (settings.json) dan data setiap fitur (data/clip = proyek & transkrip)
```

## Mengubah tampilan (khusus pengembang)

Pemakai biasa tidak perlu Node.js: tampilan yang sudah jadi ada di folder `web/`. Node.js 20.9 atau lebih baru hanya dibutuhkan bila ingin mengubah tampilan.

1. Sekali saja: buka terminal di folder `frontend` lalu jalankan `npm install`.
2. Jalankan backend dengan izin untuk server pengembangan, lalu server tampilan:
   ```
   set NERO_DEV_ORIGINS=localhost:3000
   run.bat
   ```
   Di terminal lain, dari folder `frontend`: `npm run dev`, lalu buka http://localhost:3000. Perubahan kode langsung terlihat; permintaan `/api` dan `/out` diteruskan ke app.py di port 7860.
3. Setelah selesai: `npm run build` di folder `frontend`. Hasilnya otomatis disalin ke `web/`, lalu `run.bat` memakai tampilan baru.

### Menambah fitur baru

Setiap fitur berdiri sendiri, jadi fitur baru tidak mengganggu yang lama:

1. **Backend**: buat folder `features/<id>/` (contoh: `features/clip/`). Isinya menyediakan `ID`, `NAME`, `SETTINGS`, `bp` (Flask Blueprint), `start()`, dan `summary()`; rinciannya ada di `features/__init__.py`. Tambahkan fiturnya ke daftar `FEATURES` di berkas itu. Rute otomatis berada di bawah `/api/<id>`, data di `data/<id>/` (`common.data_dir`), hasil di `output/<id>/` (`common.output_dir`), dan pengaturan khusus di bagian `"<id>"` pada `data/settings.json`. API key Claude dibaca lewat `common.feature_settings("<id>")["api_key"]`.
2. **Tampilan**: taruh kodenya di `frontend/src/features/<id>/`, buat halaman `frontend/src/app/<id>/page.tsx`, lalu tambahkan satu entri di `frontend/src/features/index.ts`. Menu samping dan kartu di Beranda langsung memuatnya (angka di kartu diambil dari `summary()`).

### Tes otomatis

Dari folder `Nero`:

```
.venv\Scripts\python -m unittest discover -s tests -t .
```

Tes memakai transkrip, video, dan folder buatan (tidak menyentuh isi folder `data/` atau `output/` Anda), termasuk memindahkan data ClipMaker versi lama dan me-render beberapa clip bergaya diketahui lalu membacanya kembali dengan "Tiru gaya". Butuh sekitar 1 menit.
