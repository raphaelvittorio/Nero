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
3. Selesai. Ikon **Nero** muncul di Desktop dan Start Menu. Butuh koneksi internet dan ruang disk kurang lebih 3 GB.

## Memakai Nero

1. Klik dua kali ikon **Nero** di Desktop (atau cari "Nero" di Start Menu). Browser akan terbuka di `http://127.0.0.1:7860`. Tidak ada jendela hitam: Nero berjalan diam-diam sampai dimatikan.
   - Bila Nero sudah berjalan, ikon cukup membuka halamannya lagi (misalnya setelah tab browser tertutup).
   - Ikon belum ada (mis. pindah dari versi lama)? Jalankan **run.bat** sekali, buka **Pengaturan**, lalu klik **Buat ikon di Desktop**.
   - **run.bat** tetap bisa dipakai bila ingin melihat pesan Nero di jendela hitam. Saat dibuka lewat ikon, pesan yang sama ditulis ke `data\nero.log`.
2. Halaman pertama adalah **Beranda**: ringkasan semua fitur (berapa tugas sedang berjalan, berapa hasil yang sudah jadi). Pilih fitur dari kartu di Beranda atau dari menu di kiri (di layar kecil: menu di atas).
3. Di bawah menu ada:
   - **Folder hasil**: membuka folder `output`. Setiap fitur punya subfoldernya sendiri, mis. `output\clip`.
   - **Pengaturan**: pengaturan umum yang dipakai semua fitur (Claude API key, model AI, cookies browser), ikon Nero di Desktop, dan **Jalankan otomatis saat Windows menyala** (Nero langsung siap di latar belakang tanpa membuka browser; buka halamannya lewat ikon Nero).
   - **Matikan Nero**: menghentikan Nero. Menutup tab browser saja tidak mematikan Nero.
   - Tanda **Terhubung** / **Terputus** (bila terputus, Nero sedang mati: buka lagi lewat ikon Nero) dan apakah **AI Claude** aktif.

### Pindah dari ClipMaker versi lama

Cukup timpa berkas aplikasinya (folder `data` dan `output` jangan dihapus). Saat pertama dibuka, Nero otomatis memindahkan proyek lama ke `data\clip\projects` dan hasil render lama ke `output\clip`; pengaturan dan API key tetap terbawa. Bila ada berkas yang sedang dibuka program lain, berkas itu dilewati dan dipindah saat Nero dibuka berikutnya (jendela run.bat atau `data\nero.log` memberi tahu).

Folder aplikasi boleh diganti namanya (mis. `ClipMaker` menjadi `Nero`); tidak perlu instal ulang. Setelah folder dipindah atau diganti namanya, jalankan **run.bat** sekali: ikon Nero di Desktop otomatis diarahkan ke lokasi baru.

## Clip Maker

Buka **Clip Maker** dari menu.

1. **Masukkan video**: tempel satu atau banyak link (satu per baris), atau tarik file video dari komputer. Tentukan jumlah clip, **bahasa** yang diucapkan di video, dan **Gaya video ini** (biarkan "Gaya aktif", atau pilih gaya lain khusus untuk video ini), lalu tekan **Proses**.
2. Aplikasi akan mengunduh, membuat transkrip, dan mencari momen paling menarik. Setiap momen diberi **skor** dan **alasan**. Proses yang sedang berjalan bisa dihentikan dengan **✕ Batal**.
3. Periksa daftar clip:
   - Ubah judul/hook (teks yang tampil di atas video).
   - Geser waktu mulai/selesai, atau pakai tombol −1 / +1 detik.
   - **Pratinjau** untuk menonton bagian aslinya.
   - **Transkrip** untuk memilih kalimat sendiri lalu menjadikannya clip.
   - **Subtitle** untuk mengoreksi kata yang salah dengar (nama orang, istilah, bahasa gaul). Waktu tiap kata tetap dipakai, jadi sebaiknya hanya mengganti kata, jangan menambah/menghapus banyak. Koreksi tersimpan di transkrip proyek, jadi ikut berlaku untuk clip lain di bagian yang sama. Clip yang sudah dirender diberi tanda **Subtitle diubah, render ulang**.
   - Hapus centang clip yang tidak ingin dirender.
4. Pilih gaya (lihat **Gaya video** di bawah), lalu tekan **Render**. Analisis video lain tetap bisa berjalan bersamaan dengan render. Gaya satu video bisa diganti kapan saja lewat pilihan gaya di baris tombol proyeknya; clip yang sudah dirender perlu dirender ulang.
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

### Gaya video

Kartu **2. Gaya video** berisi:

- **Gaya aktif**: dipakai untuk semua video, kecuali video yang diberi gaya sendiri. **Atur detail** membuka pengaturan lengkap dengan pratinjau langsung di sebelahnya; setiap perubahan tersimpan otomatis. **Simpan** menyimpan gaya aktif ke Gaya saya.
- **Tiru gaya dari clip**: baca gaya editing dari clip orang lain (lihat bagian berikut).
- **Gaya saya**: semua gaya yang pernah Anda baca dari clip atau simpan sendiri. **Siap pakai**: 11 gaya bawaan (Klasik Kuning, Tegas Hijau, Kotak Ungu, Karaoke Biru, Satu Kata Cepat, Minimalis Putih, Gaya Berita, Sinematik, Santai Lucu, Neon Pink, Hitam Putih). Klik gambar untuk memakainya; tombol **ⓘ** di pojok gambar untuk melihat detail, mengganti nama, membaca ulang, atau menghapus.

Watermark @akun, letaknya, dan perataan volume adalah milik Anda: tidak berubah saat gaya diganti.

Pilihan di **Atur detail**:

| Bagian | Pilihan |
|---|---|
| Subtitle | Font (Impact, Anton, Bebas Neue, Montserrat, Poppins, Arial Black, Segoe UI Black, Bahnschrift, Verdana, Georgia, Comic Sans; contohnya tampil dengan huruf aslinya), warna teks & warna sorotan (9 warna), **cara menyorot kata** (kata berwarna, kotak berwarna di belakang kata, karaoke, tanpa sorotan), kata per tampilan (1–4), **animasi muncul** (pop, memantul, naik perlahan, tanpa), **garis tepi** (tanpa/tipis/sedang/tebal), ukuran, posisi, HURUF BESAR, sorot kata kunci & angka, bayangan, kotak gelap di belakang subtitle |
| Judul | Ada/tidak, kotak putih/kuning/merah/hitam atau tulisan saja, lama tampil, **ukuran**, **posisi** |
| Video & efek | Tata letak (ikuti wajah, dua orang, video utuh + latar blur, **video utuh + latar hitam**, potong tengah), **zoom** (pelan maju-mundur, atau **zoom hentak** yang berganti dekat/jauh di akhir kalimat seperti jump cut), **filter warna** (cerah, hangat, dingin, sinematik, pudar, hitam putih), hapus jeda diam, progress bar di bawah atau **di atas** |
| Watermark & suara | Watermark @akun di bawah atau di atas, ratakan volume suara |

**Sorot kata kunci**: angka dan kata pemancing perhatian (rahasia, ternyata, juta, gagal, dll.) selalu berwarna sorotan dan sedikit lebih besar. **Hapus jeda**: diam lebih dari 0,3 atau 0,6 detik dibuang otomatis; audio tetap sinkron dan `.srt` ikut menyesuaikan.

### Tiru gaya dari clip referensi (AI lokal gratis)

Klik **Tiru gaya dari clip**, tempel link clip yang gaya editannya ingin ditiru (TikTok/Reels/Shorts) lalu tekan **Baca gaya**, atau **Pilih file**. Pembacaan berjalan di latar belakang (jendelanya boleh ditutup) dalam dua lapis:

1. **Pengukuran piksel** (selalu, tanpa AI): posisi & ukuran subtitle, jumlah kata per tampilan, HURUF BESAR, warna teks & sorotan, judul (ada/tidak, warna kotak, lama tampil), progress bar, tata letak (termasuk latar hitam), **zoom hentak / zoom pelan**, dan video hitam-putih.
2. **AI lokal gratis** (bila sudah disiapkan): melihat beberapa frame, potongan area subtitle, dan lembar contoh font Nero, lalu menilai **jenis font**, **cara menyorot kata** (warna/kotak/karaoke), garis tepi, bayangan, kotak gelap, gaya judul, nuansa warna, plus memberi **nama** dan **ringkasan** gayanya.

Angka hasil pengukuran selalu didahulukan; AI mengisi yang tidak bisa diukur. Di hasilnya, setiap pengaturan diberi tanda **UKUR** (diukur dari piksel) atau **AI**. Semua hasil bacaan **otomatis tersimpan di Gaya saya**, jadi bisa dipilih lagi kapan saja; tekan **Pakai gaya ini** untuk langsung memakainya. Gaya dari link bisa **dibaca ulang** (mis. setelah AI lokal disiapkan) lewat tombol **ⓘ** → **Baca ulang**.

**Menyiapkan AI lokal (sekali saja, gratis):**

1. Unduh & pasang **Ollama** dari https://ollama.com/download, lalu buka aplikasinya (berjalan di latar belakang).
2. Di Nero buka **Pengaturan** (menu kiri bawah) → bagian **AI lokal gratis**, tekan **Cek lagi**, lalu **Unduh** salah satu model:
   - **qwen3-vl:4b-instruct** (± 3,3 GB): disarankan. Di RTX 3050 4 GB ± 35 detik per clip; nama & ringkasan gayanya paling rapi.
   - **qwen3-vl:2b-instruct** (± 1,9 GB): ± 3× lebih cepat (± 12 detik per clip) dengan hasil pengaturan yang hampir sama, tetapi nama & ringkasannya kurang bagus. Cocok untuk laptop tanpa GPU.
   - **qwen3-vl:8b-instruct** (± 6 GB): paling teliti, butuh GPU 8 GB atau lebih.

   Pakai versi berakhiran **-instruct**. Tag `qwen3-vl:4b` tanpa akhiran adalah versi *thinking* yang selalu "berpikir" ribuan kata dulu, sehingga satu clip bisa 5–10 menit; Nero menghentikannya dan memberi tahu bila model seperti itu terpilih.
3. Selesai. Tanda **AI lokal siap** muncul di kartu Gaya video. Pertama kali membaca bisa 1–3 menit selagi model dimuat; berikutnya lebih cepat.

Video tidak dikirim ke internet: AI berjalan di komputer Anda. Setelah membaca, model dilepas dari memori GPU dalam 1 menit supaya transkrip video tetap memakai GPU. Bila kedua model terpasang, **Otomatis** memakai yang 4B; pilih yang lain di **Model yang dipakai**. Server lain yang meniru API OpenAI (mis. LM Studio di `http://127.0.0.1:1234`) juga bisa dipakai: isi **Alamat server** di Pengaturan.

Batasannya: hanya untuk video vertikal 9:16, dan pengukuran paling akurat untuk subtitle ber-outline hitam (gaya TikTok umumnya). Musik, b-roll, stiker, dan emoji tidak ditiru. AI kecil kadang salah menebak font atau warna, jadi periksa pratinjaunya; semua pengaturan bisa diubah di **Atur detail**. Bila video aslinya banyak tulisan (slide, berita), hasil subtitle/judul bisa keliru.

Setelah semua clip selesai, tekan **🧹 Hapus video sumber** untuk menghemat disk (video asli bisa ratusan MB). Hasil render tetap aman, tetapi clip proyek itu tidak bisa dirender ulang.

### Kemampuan Clip Maker

- Deteksi momen menarik otomatis (hook kalimat pembuka, pertanyaan, kata kunci emosional, energi suara, kepadatan bicara)
- Subtitle otomatis gaya TikTok: 1–4 kata per tampilan, sorotan warna / kotak / karaoke, animasi muncul
- 11 gaya siap pakai, pustaka **Gaya saya**, dan tiru gaya dari clip referensi dengan AI lokal gratis
- Efek video: zoom hentak / zoom pelan, filter warna, latar blur atau hitam
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

Ada dua jenis AI, keduanya opsional:

- **AI lokal gratis (Ollama)**: berjalan di komputer Anda, tanpa API key. Di Clip Maker dipakai untuk membaca & meniru gaya editing dari clip referensi. Cara menyiapkannya ada di bagian *Tiru gaya dari clip referensi*.
- **Claude API key** (berbayar): dijelaskan di bawah.

Tanpa pengaturan apa pun, setiap fitur bekerja dengan algoritma lokal (gratis); di Clip Maker, momen dipilih otomatis di komputer Anda. Untuk hasil yang jauh lebih bagus (di Clip Maker: pemilihan momen, judul hook, dan caption), isi **Claude API key** di **Pengaturan** (menu kiri bawah). Kunci ini dipakai bersama oleh semua fitur. Kunci bisa dibuat di https://console.anthropic.com (berbayar per pemakaian; satu video biasanya hanya beberapa sen dolar). Kunci hanya disimpan di komputer Anda (`data/settings.json`).

## Tips & masalah umum

| Masalah | Solusi |
|---|---|
| Unduhan YouTube gagal / "confirm you're not a bot" | Di **Pengaturan** (menu kiri bawah), isi "Ambil cookies dari browser" dengan browser tempat Anda login YouTube (chrome/edge/firefox). Tutup browser itu saat mengunduh. |
| Unduhan tiba-tiba gagal padahal dulu bisa | Jalankan **update.bat** (situs video sering berubah). |
| Ikon Nero diklik tetapi halaman tidak terbuka | Jalankan **run.bat** untuk melihat pesannya, atau buka `data\nero.log`. |
| Transkrip lambat | Lihat baris di bawah tombol Proses: bila tertulis "memakai CPU" padahal ada kartu NVIDIA, jalankan **install.bat** lagi. Atau di **Pengaturan clip** ganti model transkrip ke **base**. Dengan GPU, pakai **large-v3-turbo**: hampir seakurat large-v3 tetapi jauh lebih cepat. |
| Subtitle kurang tepat / malah diterjemahkan | Pastikan pilihan **Bahasa** saat menambahkan video sesuai bahasa yang diucapkan (atau pilih Deteksi otomatis), dan pakai model **medium**. |
| Wajah tidak diikuti | Pilih tata letak **Ikuti wajah**, **Dua orang (atas/bawah)** untuk podcast, atau **Video utuh + latar blur** untuk video dengan banyak orang. |
| "AI lokal belum berjalan" saat tiru gaya | Buka aplikasi Ollama (ikonnya ada di Start Menu), lalu di **Pengaturan** tekan **Cek lagi**. Gaya tetap bisa dibaca tanpa AI, hanya font & cara menyorot kata yang tidak ditiru. |
| AI lokal lambat / "memori tidak cukup" | Pilih model yang lebih kecil (**qwen3-vl:2b-instruct**) di **Pengaturan → AI lokal gratis**. |
| "Model selalu berpikir panjang" | Model yang terpilih adalah versi *thinking*. Unduh versi **-instruct** lalu pilih di Pengaturan. |

Gunakan aplikasi ini untuk video milik Anda sendiri atau yang Anda punya izin untuk mengunggah ulang.

## Struktur folder

```
Nero/
  install.bat, run.bat, update.bat
  requirements*.txt daftar paket (lock = versi yang sudah teruji, gpu = pustaka CUDA)
  app.py            server web lokal: keamanan, tampilan, pengaturan umum, memuat semua fitur
  common.py         bagian bersama semua fitur (lokasi folder, pengaturan, hapus berkas)
  local_ai.py       AI lokal gratis (Ollama / LM Studio), dipakai bersama semua fitur
  desktop.py        ikon Nero di Desktop & Start Menu, buka otomatis, berjalan tanpa jendela hitam
  features/         satu folder per fitur
    clip/           Clip Maker: api.py (rute, antrian, pustaka gaya), engine.py (unduh, transkrip, momen,
                    render, ukur gaya), style_ai.py (baca gaya dengan AI lokal), presets.py (gaya siap pakai)
  web/              tampilan aplikasi siap pakai (hasil build frontend/, jangan diubah langsung)
  frontend/         kode sumber tampilan: Next.js + TypeScript + Tailwind CSS + shadcn/ui
  models/           model deteksi wajah
  fonts/            font subtitle gratis (lisensi SIL OFL, berkas OFL-*.txt)
  tests/            tes otomatis
  output/           HASIL ANDA, satu subfolder per fitur (output/clip = video clip)
  data/             pengaturan (settings.json), catatan nero.log, dan data setiap fitur (data/clip = proyek & transkrip)
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

Untuk mencoba tanpa menyentuh data Anda, jalankan Nero kedua dengan folder data terpisah: variabel `NERO_DATA` dan `NERO_OUTPUT` (mis. `data-uji\data` dan `data-uji\output`, folder `data-uji/` tidak ikut git) dan `PORT=7861`. Konfigurasi `nero-uji` & `nero-ui-uji` di `.claude/launch.json` sudah mengaturnya.

### Menambah fitur baru

Setiap fitur berdiri sendiri, jadi fitur baru tidak mengganggu yang lama:

1. **Backend**: buat folder `features/<id>/` (contoh: `features/clip/`). Isinya menyediakan `ID`, `NAME`, `SETTINGS`, `bp` (Flask Blueprint), `start()`, dan `summary()`; rinciannya ada di `features/__init__.py`. Tambahkan fiturnya ke daftar `FEATURES` di berkas itu. Rute otomatis berada di bawah `/api/<id>`, data di `data/<id>/` (`common.data_dir`), hasil di `output/<id>/` (`common.output_dir`), dan pengaturan khusus di bagian `"<id>"` pada `data/settings.json`. API key Claude dibaca lewat `common.feature_settings("<id>")["api_key"]`.
2. **Tampilan**: taruh kodenya di `frontend/src/features/<id>/`, buat halaman `frontend/src/app/<id>/page.tsx`, lalu tambahkan satu entri di `frontend/src/features/index.ts`. Menu samping dan kartu di Beranda langsung memuatnya (angka di kartu diambil dari `summary()`).

### Tes otomatis

Dari folder `Nero`:

```
.venv\Scripts\python -m unittest discover -s tests -t .
```

Tes memakai transkrip, video, dan folder buatan (tidak menyentuh isi folder `data/` atau `output/` Anda), termasuk memindahkan data ClipMaker versi lama, me-render beberapa clip bergaya diketahui lalu membacanya kembali dengan "Tiru gaya", dan Ollama palsu untuk menguji jalur AI lokal tanpa internet. Butuh sekitar 1,5 menit.
