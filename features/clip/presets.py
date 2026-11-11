"""
Nero · Clip Maker - gaya video siap pakai (preset bawaan) dan aturan menyimpan gaya.

Gaya = semua pengaturan tampilan clip (subtitle, judul, efek, tata letak). Watermark @akun & perataan
volume adalah milik pengguna, bukan bagian gaya: tidak ikut disimpan, dan tidak berubah saat gaya diganti.
"""
from __future__ import annotations

# Nilai bawaan semua kunci gaya. Kunci baru selalu punya nilai yang sama dengan perilaku lama,
# jadi gaya yang tersimpan sebelum kunci itu ada tetap terlihat sama.
DEFAULT_STYLE = {
    "layout": "auto", "captions": True, "caption_color": "kuning", "caption_upper": True,
    "caption_size": 86, "caption_pos": 0.68, "caption_words": 3,
    "title_on": True, "title_secs": 0, "title_bg": "putih", "title_size": 64, "title_pos": 0.11,
    "progress_bar": True, "progress_pos": "bawah", "handle": "", "handle_pos": "bawah", "loudnorm": True,
    "caption_font": "impact", "caption_base": "putih", "caption_emphasis": False, "cut_pauses": 0,
    "caption_highlight": "warna", "caption_anim": "pop", "caption_stroke": 2, "caption_shadow": True,
    "caption_box": False, "zoom": "tanpa", "filter": "asli",
}
PERSONAL_KEYS = ("handle", "handle_pos", "loudnorm")


def look_of(style: dict) -> dict:
    """Bagian gaya yang disimpan/dipertukarkan (tanpa pengaturan pribadi)."""
    return {k: v for k, v in {**DEFAULT_STYLE, **style}.items() if k in DEFAULT_STYLE and k not in PERSONAL_KEYS}


def apply_look(current: dict, look: dict) -> dict:
    """Gaya aktif baru: tampilan dari `look`, pengaturan pribadi tetap dari gaya sekarang."""
    out = {**DEFAULT_STYLE, **look_of(look)}
    for k in PERSONAL_KEYS:
        out[k] = current.get(k, DEFAULT_STYLE[k])
    return out


def _p(pid, name, summary, **kw):
    return {"id": f"preset:{pid}", "name": name, "summary": summary, "preset": True,
            "style": look_of(kw)}


PRESETS = [
    _p("klasik", "Klasik Kuning",
       "Subtitle Impact putih, kata yang diucapkan kuning, judul kotak putih. Gaya podcast yang paling umum."),
    _p("tegas-hijau", "Tegas Hijau",
       "Dua kata besar per tampilan dengan sorotan hijau, kata kunci membesar, dan zoom hentak tiap kalimat.",
       caption_font="anton", caption_color="hijau", caption_words=2, caption_size=104, caption_emphasis=True,
       caption_anim="bounce", caption_stroke=3, title_on=False, zoom="hentak", cut_pauses=0.3),
    _p("kotak-ungu", "Kotak Ungu",
       "Kata yang diucapkan diberi kotak ungu, huruf biasa, Poppins. Rapi dan modern.",
       caption_font="poppins", caption_highlight="kotak", caption_color="ungu", caption_upper=False,
       caption_size=80, caption_stroke=1, title_bg="hitam", title_secs=5),
    _p("karaoke-biru", "Karaoke Biru",
       "Empat kata per tampilan, kata yang sudah diucapkan berubah biru seperti karaoke.",
       caption_font="montserrat", caption_highlight="karaoke", caption_color="biru", caption_words=4,
       caption_size=78, title_bg="putih", title_secs=3),
    _p("satu-kata", "Satu Kata Cepat",
       "Satu kata besar per tampilan yang memantul masuk; angka & kata penting kuning. Cocok untuk tempo cepat.",
       caption_font="impact", caption_words=1, caption_size=118, caption_color="kuning", caption_highlight="tanpa",
       caption_emphasis=True, caption_anim="bounce", caption_pos=0.6, title_on=False, cut_pauses=0.3),
    _p("minimalis", "Minimalis Putih",
       "Subtitle putih huruf biasa di atas kotak gelap transparan, tanpa sorotan. Bersih dan tenang.",
       caption_font="segoe", caption_highlight="tanpa", caption_color="putih", caption_upper=False,
       caption_words=4, caption_size=70, caption_stroke=0, caption_box=True, caption_anim="naik",
       caption_pos=0.72, title_bg="tanpa", title_size=58, progress_bar=False),
    _p("berita", "Gaya Berita",
       "Font berkait Georgia di kotak gelap, judul kotak merah, progress bar di atas. Kesan serius & tepercaya.",
       caption_font="georgia", caption_highlight="tanpa", caption_color="putih", caption_upper=False,
       caption_words=4, caption_size=72, caption_stroke=1, caption_box=True, caption_pos=0.74,
       title_bg="merah", title_size=60, progress_pos="atas", layout="blur"),
    _p("sinematik", "Sinematik",
       "Warna sinematik dengan sudut gelap, zoom pelan, subtitle ramping putih. Cocok untuk cerita & motivasi.",
       caption_font="bahnschrift", caption_highlight="tanpa", caption_color="putih", caption_words=3,
       caption_size=84, caption_stroke=1, caption_anim="naik", filter="sinematik", zoom="halus",
       title_bg="tanpa", title_secs=5, progress_bar=False),
    _p("santai", "Santai Lucu",
       "Comic Sans tebal dengan sorotan oranye yang memantul. Pas untuk konten lucu & ringan.",
       caption_font="comic", caption_color="oranye", caption_upper=False, caption_size=84,
       caption_anim="bounce", title_bg="kuning", filter="cerah"),
    _p("neon-pink", "Neon Pink",
       "Huruf tinggi Anton dengan sorotan pink, warna video lebih cerah, zoom hentak.",
       caption_font="anton", caption_color="pink", caption_words=2, caption_size=100, caption_emphasis=True,
       filter="cerah", zoom="hentak", title_bg="hitam"),
    _p("hitam-putih", "Hitam Putih",
       "Video hitam-putih dengan subtitle kuning menyala dan latar hitam. Dramatis.",
       caption_font="bebas", caption_color="kuning", caption_base="kuning", caption_highlight="tanpa",
       caption_size=96, caption_words=3, filter="hitamputih", layout="hitam", title_bg="tanpa"),
]
PRESET_BY_ID = {p["id"]: p for p in PRESETS}
