# ClipMaker — Panduan Singkat

Aplikasi pribadi untuk mengubah video panjang (dari link atau file) menjadi video pendek vertikal 9:16 yang siap diunggah ke TikTok, Instagram Reels, dan YouTube Shorts. Semua berjalan di komputer Anda sendiri.

## Instalasi (sekali saja)

1. Ekstrak folder `ClipMaker` ke tempat yang mudah, misalnya `D:\ClipMaker`.
2. Klik dua kali **install.bat**. Ia akan menginstal Python, FFmpeg, Deno (dibutuhkan untuk unduhan YouTube), paket yang diperlukan, dan model transkrip (sekitar 500 MB).
   - Jika muncul pesan "Python selesai diinstal", tutup jendelanya lalu jalankan **install.bat** sekali lagi.
3. Selesai. Butuh koneksi internet dan ruang disk kurang lebih 3 GB.

## Cara pakai

1. Klik dua kali **run.bat**. Browser akan terbuka di `http://127.0.0.1:7860`. Biarkan jendela hitam tetap terbuka selama memakai aplikasi.
2. **Masukkan video**: tempel satu atau banyak link (satu per baris), atau tarik file video dari komputer. Tentukan jumlah clip, lalu tekan **Proses**.
3. Aplikasi akan mengunduh, membuat transkrip, dan mencari momen paling menarik. Setiap momen diberi **skor** dan **alasan**.
4. Periksa daftar clip:
   - Ubah judul/hook (teks yang tampil di atas video).
   - Geser waktu mulai/selesai, atau pakai tombol −1 / +1 detik.
   - **Pratinjau** untuk menonton bagian aslinya.
   - **Transkrip** untuk memilih kalimat sendiri lalu menjadikannya clip.
   - Hapus centang clip yang tidak ingin dirender.
5. Atur **Gaya video** (berlaku untuk semua render berikutnya), lalu tekan **Render**.
6. Hasil muncul di daftar dan tersimpan di folder `output`. Untuk setiap clip ada:
   - `.mp4` video 1080×1920 siap upload
   - `.srt` subtitle terpisah
   - `_caption.txt` caption postingan + hashtag (tombol **Caption** juga menyalinnya)

Centang **Langsung render otomatis** bila ingin semua momen langsung dijadikan video tanpa diperiksa dulu.

## Fitur

- Deteksi momen menarik otomatis (hook kalimat pembuka, pertanyaan, kata kunci emosional, energi suara, kepadatan bicara)
- Subtitle otomatis gaya TikTok: 1–4 kata per tampilan, kata yang diucapkan disorot warna, efek muncul
- Crop pintar 9:16 mengikuti wajah pembicara dengan gerakan kamera halus
- Tata letak alternatif: video utuh dengan latar blur, atau potong tengah
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
| Transkrip lambat | Di **Pengaturan**, ganti model transkrip ke **base**. Jika punya kartu grafis NVIDIA, model **medium/large-v3** akan berjalan cepat. |
| Subtitle kurang tepat | Pakai model **medium**, dan pastikan "Bahasa video" sudah benar. |
| Wajah tidak diikuti | Pilih tata letak **Ikuti wajah**, atau **Video utuh + latar blur** untuk video dengan banyak orang. |

Gunakan aplikasi ini untuk video milik Anda sendiri atau yang Anda punya izin untuk mengunggah ulang.

## Struktur folder

```
ClipMaker/
  install.bat, run.bat, update.bat
  app.py            server web lokal
  clipper_core.py   mesin unduh, transkrip, deteksi momen, render
  web/index.html    tampilan aplikasi
  models/           model deteksi wajah
  output/           HASIL VIDEO ANDA
  data/             proyek, transkrip, pengaturan
```
