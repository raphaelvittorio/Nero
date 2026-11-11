"""Edit subtitle & hapus jeda (logika waktu, tanpa render)."""
import copy
import unittest

from tests.util import fake_segments

from features.clip import engine as core  # noqa: E402


def seg(words, t0):
    ws, t = [], t0
    for w in words.split():
        ws.append({"start": round(t, 2), "end": round(t + 0.4, 2), "word": w})
        t += 0.5
    return {"start": ws[0]["start"], "end": ws[-1]["end"], "text": words, "words": ws}


BASE = [seg("halo semua nama saya rafel", 0.0), seg("hari ini kita bahas saham", 3.0), seg("sampai jumpa", 6.0)]


class EditWords(unittest.TestCase):
    def test_ganti_kata_waktunya_tetap(self):
        s = copy.deepcopy(BASE)
        n = core.edit_words(s, 1.0, 5.6, "nama saya Raphael hari ini kita bahas saham-saham")
        self.assertEqual(n, 2)
        self.assertEqual(s[0]["text"], "halo semua nama saya Raphael")
        self.assertEqual(s[1]["text"], "hari ini kita bahas saham-saham")
        self.assertEqual(s[2], BASE[2])
        self.assertEqual((s[0]["words"][-1]["start"], s[0]["words"][-1]["end"]), (2.0, 2.4))

    def test_sisip_dan_hapus(self):
        s = copy.deepcopy(BASE)
        core.edit_words(s, 3.0, 5.6, "hari ini kita akan bahas")
        w = s[1]["words"]
        self.assertEqual(s[1]["text"], "hari ini kita akan bahas")
        self.assertTrue(all(a["start"] <= b["start"] and a["end"] <= b["start"] + 1e-9 for a, b in zip(w, w[1:])))

    def test_tanpa_perubahan(self):
        s = copy.deepcopy(BASE)
        self.assertEqual(core.edit_words(s, 0, 9, core.clip_words_text(s, 0, 9)), 0)
        self.assertEqual(s, BASE)

    def test_kosong_ditolak(self):
        with self.assertRaises(ValueError):
            core.edit_words(copy.deepcopy(BASE), 0, 9, "   ")


class ClipTimeline(unittest.TestCase):
    WORDS = [{"start": 0.2, "end": 0.6, "word": "a"}, {"start": 0.7, "end": 1.0, "word": "b"},
             {"start": 3.0, "end": 3.4, "word": "c"}, {"start": 3.5, "end": 3.9, "word": "d"}]

    def test_tanpa_hapus_jeda(self):
        keep, rel = core.clip_timeline(self.WORDS, 0.0, 5.0, {"cut_pauses": 0})
        self.assertEqual(keep, [(0, 150)])
        self.assertEqual(rel[2]["start"], 3.0)

    def test_jeda_panjang_dibuang(self):
        keep, rel = core.clip_timeline(self.WORDS, 0.0, 5.0, {"cut_pauses": 0.5})
        self.assertEqual(len(keep), 2)
        self.assertLess(rel[2]["start"], 2.0)                       # jeda 2 detik tinggal ~0,24 detik
        self.assertAlmostEqual(rel[3]["start"] - rel[2]["start"], 0.5, delta=0.04)  # jarak antarkata tetap
        self.assertTrue(all(isinstance(k, int) and isinstance(m, int) for k, m in keep))  # batas = frame

    def test_jeda_pendek_dipertahankan(self):
        segs = fake_segments(80, gap_every=0)
        words = [w for s in segs for w in s["words"]]
        keep, _ = core.clip_timeline(words, words[0]["start"], words[-1]["end"], {"cut_pauses": 0.6})
        self.assertEqual(len(keep), 1)


if __name__ == "__main__":
    unittest.main()
