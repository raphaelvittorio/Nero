"""Data uji buatan: transkrip palsu (tidak memakai folder data/ milik pengguna)."""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

VOCAB = ("kenapa bisnis pertama saya bangkrut padahal modal besar ternyata rahasia uang juta orang kerja "
         "pasar harga naik turun cerita teman kantor pabrik tutup ekonomi rumah beli jual untung rugi "
         "sekarang dulu waktu tahun belajar gagal sukses coba lagi pelan cepat murah mahal kota desa").split()


def fake_segments(n_words=600, seed=7, rate=2.6, gap_every=0, gap=1.5):
    """Segmen ala faster-whisper: {start, end, text, words:[{start, end, word}]}.
    gap_every > 0 menyisipkan jeda `gap` detik setiap sekian kata."""
    rnd = random.Random(seed)
    t, segs, cur = 0.5, [], []
    for i in range(n_words):
        w = rnd.choice(VOCAB)
        d = 0.18 + 0.05 * len(w) / 3
        cur.append({"start": round(t, 2), "end": round(t + d, 2), "word": w})
        t += 1 / rate
        if gap_every and (i + 1) % gap_every == 0:
            t += gap
        if len(cur) >= 12 or rnd.random() < 0.08:
            cur[-1]["word"] += "."
            segs.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                         "text": " ".join(x["word"] for x in cur), "words": cur})
            cur = []
    if cur:
        segs.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                     "text": " ".join(x["word"] for x in cur), "words": cur})
    return segs
