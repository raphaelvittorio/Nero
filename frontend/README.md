# ClipMaker — tampilan

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

Saat `npm run dev`, jalankan app.py dengan `CLIPMAKER_DEV_ORIGINS=localhost:3000` supaya
permintaan POST dari server pengembangan tidak ditolak oleh pemeriksaan asal (CSRF).
Alamat backend bisa diganti dengan variabel `CLIPMAKER_API`.

## Susunan kode

- `src/app/` — layout dan halaman tunggal
- `src/components/clipmaker/` — fitur aplikasi: kartu input, gaya, proyek, clip, dialog, state bersama (`store.tsx`)
- `src/components/ui/` — komponen shadcn/ui
- `src/lib/` — tipe data API, helper `api()`, format waktu, daftar pilihan
