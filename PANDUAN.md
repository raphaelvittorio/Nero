# ClipMaker — Panduan Singkat

Aplikasi pribadi untuk mengubah video panjang (dari link atau file) menjadi video pendek vertikal 9:16 yang siap diunggah ke TikTok, Instagram Reels, dan YouTube Shorts. Semua berjalan di komputer Anda sendiri.

## Instalasi (sekali saja)

1. Ekstrak folder `ClipMaker` ke tempat yang mudah, misalnya `D:\ClipMaker`.
2. Klik dua kali **install.bat**. Ia akan menginstal Python, FFmpeg, Deno (dibutuhkan untuk unduhan YouTube), paket yang diperlukan, dan model transkrip (sekitar 500 MB). Bila komputer punya kartu grafis NVIDIA, pustaka CUDA (sekitar 1 GB) ikut dipasang supaya transkrip jauh lebih cepat.
   - Jika muncul pesan "Python selesai diinstal", tutup jendelanya lalu jalankan **install.bat** sekali lagi.
3. Selesai. Butuh koneksi internet dan ruang disk kurang lebih 3 GB.

## Cara pakai

1. Klik dua kali **run.bat**. Browser akan terbuka di `http://127.0.0.1:7860`. Biarkan jendela hitam tetap terbuka selama memakai aplikasi.
2. **Masukkan video**: tempel satu atau banyak link (satu per baris), atau tarik file video dari komputer. Tentukan jumlah clip dan **bahasa** yang diucapkan di video, lalu tekan **Proses**.
3. Aplikasi akan mengunduh, membuat transkrip, dan mencari momen paling menarik. Setiap momen diberi **skor** dan **alasan**. Proses yang sedang berjalan bisa dihentikan dengan **✕ Batal**.
4. Periksa daftar clip:
   - Ubah judul/hook (teks yang tampil di atas video).
   - Geser waktu mulai/selesai, atau pakai tombol −1 / +1 detik.
   - **Pratinjau** untuk menonton bagian aslinya.
   - **Transkrip** untuk memilih kalimat sendiri lalu menjadikannya clip.
   - Hapus centang clip yang tidak ingin dirender.
5. Atur **Gaya video** (berlaku untuk semua render berikutnya). Tekan **👁 Pratinjau gaya** untuk melihat hasilnya di satu frame tanpa menunggu render. Lalu tekan **Render**. Analisis video lain tetap bisa berjalan bersamaan dengan render.
6. Hasil muncul di daftar dan tersimpan di folder `output`. Untuk setiap clip ada:
   - `.mp4` video 1080×1920 siap upload
   - `.srt` subtitle terpisah
   - `_caption.txt` caption postingan + hashtag (tombol **Caption** juga menyalinnya)

Centang **Langsung render otomatis** bila ingin semua momen langsung dijadikan video tanpa diperiksa dulu.

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

Di bawah kolom muncul daftar **Dikenali** supaya Anda bisa memastikan setiap baris terbaca dengan benar. **Jumlah clip** adalah total: timeline dan titik Anda selalu masuk, sisanya diisi momen pilihan otomatis. Bila hanya ingin clip dari riset Anda, isi Jumlah clip sama dengan banyaknya timeline. Clip dari referensi diberi tanda **Timeline Anda**, **Titik riset Anda**, atau **Sama dengan clip referensi**.

Setelah semua clip selesai, tekan **🧹 Hapus video sumber** untuk menghemat disk (video asli bisa ratusan MB). Hasil render tetap aman, tetapi clip proyek itu tidak bisa dirender ulang.

## Fitur

- Deteksi momen menarik otomatis (hook kalimat pembuka, pertanyaan, kata kunci emosional, energi suara, kepadatan bicara)
- Subtitle otomatis gaya TikTok: 1–4 kata per tampilan, kata yang diucapkan disorot warna, efek muncul
- Crop pintar 9:16 mengikuti wajah pembicara dengan gerakan kamera halus
- Tata letak **Dua orang (atas/bawah)** untuk podcast/wawancara: tiap orang mendapat setengah layar (dipilih otomatis bila terdeteksi dua wajah berdampingan)
- Tata letak alternatif: video utuh dengan latar blur, atau potong tengah
- Transkrip di GPU NVIDIA bila tersedia (otomatis kembali ke CPU bila gagal)
- Judul/hook di atas video, progress bar, watermark @akun
- Volume suara diratakan sesuai standar media sosial
- Proses banyak link sekaligus dengan antrian
- Caption + hashtag siap salin

## Mode AI (opsional, lebih pintar)

Tanpa pengaturan apa pun, momen dipilih oleh algoritma lokal (gratis). Untuk pemilihan momen, judul hook, dan caption yang jauh lebih bagus, isi **Claude API key** di **Pengaturan**. Kunci bisa dibuat di https://console.anthropic.com (berbayar per pemakaian; satu video biasanya hanya beberapa sen dolar). Kunci hanya disimpan di komputer Anda (`data/settings.json`).

## Tips & masalah umum

| Masalah | Solusi |
|---|---|
| Unduhan YouTube gagal / "confirm you're not a bot" | Di **Pengaturan**, isi "Ambil cookies dari browser" dengan browser tempat Anda login YouTube (chrome/edge/firefox). Tutup browser itu saat mengunduh. |
| Unduhan tiba-tiba gagal padahal dulu bisa | Jalankan **update.bat** (situs video sering berubah). |
| Transkrip lambat | Lihat baris di bawah tombol Proses: bila tertulis "memakai CPU" padahal ada kartu NVIDIA, jalankan **install.bat** lagi. Atau di **Pengaturan** ganti model transkrip ke **base**. Dengan GPU, pakai **large-v3-turbo**: hampir seakurat large-v3 tetapi jauh lebih cepat. |
| Subtitle kurang tepat / malah diterjemahkan | Pastikan pilihan **Bahasa** saat menambahkan video sesuai bahasa yang diucapkan (atau pilih Deteksi otomatis), dan pakai model **medium**. |
| Wajah tidak diikuti | Pilih tata letak **Ikuti wajah**, **Dua orang (atas/bawah)** untuk podcast, atau **Video utuh + latar blur** untuk video dengan banyak orang. |

Gunakan aplikasi ini untuk video milik Anda sendiri atau yang Anda punya izin untuk mengunggah ulang.

## Struktur folder

```
ClipMaker/
  install.bat, run.bat, update.bat
  requirements*.txt daftar paket (lock = versi yang sudah teruji, gpu = pustaka CUDA)
  app.py            server web lokal
  clipper_core.py   mesin unduh, transkrip, deteksi momen, render
  web/              tampilan aplikasi siap pakai (hasil build frontend/, jangan diubah langsung)
  frontend/         kode sumber tampilan: Next.js + TypeScript + Tailwind CSS + shadcn/ui
  models/           model deteksi wajah
  output/           HASIL VIDEO ANDA
  data/             proyek, transkrip, pengaturan
```

## Mengubah tampilan (khusus pengembang)

Pemakai biasa tidak perlu Node.js: tampilan yang sudah jadi ada di folder `web/`. Node.js 20.9 atau lebih baru hanya dibutuhkan bila ingin mengubah tampilan.

1. Sekali saja: buka terminal di folder `frontend` lalu jalankan `npm install`.
2. Jalankan backend dengan izin untuk server pengembangan, lalu server tampilan:
   ```
   set CLIPMAKER_DEV_ORIGINS=localhost:3000
   run.bat
   ```
   Di terminal lain, dari folder `frontend`: `npm run dev`, lalu buka http://localhost:3000. Perubahan kode langsung terlihat; permintaan `/api`, `/media`, dan `/out` diteruskan ke app.py di port 7860.
3. Setelah selesai: `npm run build` di folder `frontend`. Hasilnya otomatis disalin ke `web/`, lalu `run.bat` memakai tampilan baru.
