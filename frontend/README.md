# Nero — tampilan

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui (Base UI).

Halaman ini sepenuhnya berjalan di browser dan memanggil API Flask di `../app.py`.
`npm run build` membuat file statis (`output: "export"`) lalu menyalinnya ke `../web`,
folder yang disajikan oleh `app.py`. Jadi pemakai aplikasi tidak butuh Node.js.

```bash
npm install
npm run dev        # http://localhost:3000, API diteruskan ke http://127.0.0.1:7860
npm run build      # build + salin ke ../web
npm run lint
npm run typecheck
```

Saat `npm run dev`, jalankan app.py dengan `NERO_DEV_ORIGINS=localhost:3000` supaya
permintaan POST dari server pengembangan tidak ditolak oleh pemeriksaan asal (CSRF).
Alamat backend bisa diganti dengan variabel `NERO_API`.

## Susunan kode

- `src/app/` — layout (kerangka Nero) dan halaman: `page.tsx` (Beranda), `clip/page.tsx` (Clip Maker)
- `src/components/nero/` — kerangka aplikasi: menu samping, Beranda, pengaturan umum, state bersama (`store.tsx`)
- `src/features/index.ts` — daftar fitur; menu dan kartu Beranda dibuat dari sini
- `src/features/clip/` — fitur Clip Maker: kartu input, gaya, proyek, clip, dialog, state, tipe, pilihan
- `src/components/fields.tsx` — input bersama (`SimpleSelect`, `CommitInput`)
- `src/components/ui/` — komponen shadcn/ui
- `src/lib/` — helper `api()` / `post()` / `openFolder()`, `cn()`

## Menambah fitur

1. Backend: buat `features/<id>/` (lihat `features/__init__.py`) dengan rute di bawah `/api/<id>`.
2. Tampilan: taruh kodenya di `src/features/<id>/`, buat halaman `src/app/<id>/page.tsx`,
   lalu tambahkan satu entri di `src/features/index.ts`. Menu samping dan Beranda langsung memuatnya.
