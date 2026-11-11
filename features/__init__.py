"""
Daftar fitur Nero.

Setiap fitur adalah satu folder di sini (lihat features/clip sebagai contoh) yang menyediakan:

  ID        id pendek, mis. "clip". Dipakai untuk alamat API (/api/<ID>/...), folder data/<ID>/,
            folder output/<ID>/, dan bagian pengaturan {"<ID>": {...}} di data/settings.json
  NAME      nama yang ditampilkan
  SETTINGS  nilai bawaan pengaturan khusus fitur ({} bila tidak ada)
  bp        flask.Blueprint berisi rute fitur (tanpa awalan /api/<ID>, ditambahkan app.py)
  start()   dipanggil sekali saat aplikasi dibuka (memuat data, menjalankan pekerja)
  summary() ringkasan untuk Beranda: {"busy": n, "queue": n, "stats": [{"label", "value"}]}

Fitur baru: buat foldernya, tambahkan ke FEATURES di bawah, lalu daftarkan juga tampilannya di
frontend/src/lib/features.ts.
"""
from . import clip

FEATURES = [clip]
