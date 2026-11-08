"""Kolom 'Referensi & instruksi': pembaca timeline, kata kunci, pencocokan clip referensi, pemilihan momen."""
import json
import random
import types
import unittest
from unittest import mock

import numpy as np

from tests.util import fake_segments

import clipper_core as core  # noqa: E402  (tests.util menambahkan folder aplikasi ke sys.path)


class ParseBrief(unittest.TestCase):
    def test_baris_campuran(self):
        b = core.parse_brief("""
- 12:30 - 13:45 cerita gagal bisnis pertama
2. [1:02:10 – 1:03:00] | tips mengatur uang
Clip 3: 05:00 sampai 05:40 momen lucu
12.30 - 13.15 format titik
45:20 momen lucu banget
https://www.tiktok.com/@akun/video/123?is_from_webapp=1
Fokus pada momen tentang "ekonomi china" dan investasi.
Jangan ambil bagian iklan atau sponsor.
""")
        self.assertEqual([r["start"] for r in b["ranges"]], [750, 3730, 300, 750])
        self.assertEqual([r["end"] for r in b["ranges"]], [825, 3780, 340, 795])
        self.assertEqual([r["note"] for r in b["ranges"][:3]],
                         ["cerita gagal bisnis pertama", "tips mengatur uang", "momen lucu"])
        self.assertEqual(b["points"], [{"t": 2720.0, "note": "momen lucu banget"}])
        self.assertEqual(len(b["links"]), 1)
        want, avoid = core.brief_keywords(b["instructions"])
        self.assertIn("ekonomi china", want)
        self.assertIn("investasi", want)
        self.assertIn("iklan", avoid)
        self.assertNotIn("iklan", want)

    def test_instruksi_bukan_timeline(self):
        self.assertEqual(core.parse_brief("Buat judul berupa pertanyaan, durasi pendek")["ranges"], [])
        self.assertEqual(core.parse_brief("menit 12 ada cerita")["points"], [])


class AppHelpers(unittest.TestCase):
    def test_link_youtube(self):
        import app
        self.assertEqual(app.youtube_id("https://youtu.be/vQodCxq7b9g?t=754"), "vQodCxq7b9g")
        self.assertEqual(app.youtube_id("https://www.youtube.com/watch?v=vQodCxq7b9g&t=12m34s"), "vQodCxq7b9g")
        self.assertEqual(app.url_time("https://youtu.be/x?t=754s"), 754)
        self.assertEqual(app.url_time("https://www.youtube.com/watch?v=x&t=1h2m3s"), 3723)
        self.assertIsNone(app.url_time("https://youtu.be/x?si=abc"))


class MatchReference(unittest.TestCase):
    def setUp(self):
        self.segs = fake_segments(900)
        self.words = [w for s in self.segs for w in s["words"]]

    def test_ketemu_walau_transkrip_tidak_sempurna(self):
        i0, i1 = 400, 520
        rnd = random.Random(1)
        ref = []
        for w in self.words[i0:i1 + 1]:
            r = rnd.random()
            if r < 0.08:
                continue                      # kata hilang
            ref.append("salahdengar" if r < 0.14 else w["word"])
        m = core.match_reference(self.segs, [{"start": 0, "end": 60, "text": " ".join(ref)}])
        self.assertIsNotNone(m)
        self.assertLess(abs(m["start"] - self.words[i0]["start"]), 2)
        self.assertLess(abs(m["end"] - self.words[i1]["end"]), 2)

    def test_clip_lain_tidak_cocok(self):
        other = [{"start": 0, "end": 30, "text": "review skincare murah yang bagus banget buat kulit berminyak "
                                                   "dan berjerawat ya guys jangan lupa follow"}]
        self.assertIsNone(core.match_reference(self.segs, other))


class Heuristic(unittest.TestCase):
    def test_timeline_titik_dan_otomatis(self):
        segs = fake_segments(700)
        energy = np.random.default_rng(0).normal(-25, 5, size=int(segs[-1]["end"] / 0.5) + 2)
        fixed = [{"start": 30.0, "end": 60.0, "note": "catatan saya", "ref": "timeline"}]
        out = core.find_highlights_heuristic(segs, energy, 2, 20, 60, keywords=["bisnis"],
                                             points=[{"t": 120.0, "note": "lucu"}], fixed=fixed)
        self.assertEqual(len(out), 4)
        t = next(c for c in out if c["ref"] == "timeline")
        self.assertEqual((t["start"], t["end"], t["title"]), (30.0, 60.0, "catatan saya"))
        p = next(c for c in out if c["ref"] == "titik")
        self.assertTrue(p["start"] <= 121 and p["end"] >= 124)
        for a in out:
            for b in out:
                if a is not b and a["ref"] is None:
                    self.assertFalse(core._overlaps(a["start"], a["end"], b["start"], b["end"]))

    def test_tanpa_transkrip_timeline_tetap_ada(self):
        fixed = [{"start": 1.0, "end": 20.0, "note": "", "ref": "timeline"}]
        self.assertEqual(len(core.find_highlights_heuristic([], np.array([-30.0]), 3, 20, 60, fixed=fixed)), 1)


class AIPostProcessing(unittest.TestCase):
    """Jawaban AI dirapikan: waktu timeline dari pengguna dipakai, clip tumpang tindih dibuang."""

    def test_jawaban_ai(self):
        segs = fake_segments(700)
        captured = {}
        payload = {"clips": [
            {"start": 0, "end": 0, "title": "Judul timeline", "score": 88, "reason": "r", "caption": "c",
             "hashtags": ["a b", "#c"], "ref": 1},
            {"start": 118, "end": 150, "title": "Baru", "score": 70, "reason": "r", "caption": "c",
             "hashtags": [], "ref": 0},
            {"start": 35, "end": 70, "title": "Tumpang tindih", "score": 99, "reason": "r", "caption": "c",
             "hashtags": [], "ref": 0},
        ]}

        def create(**kw):
            captured.update(kw)
            return types.SimpleNamespace(stop_reason="end_turn", content=[
                types.SimpleNamespace(type="text", text=json.dumps(payload))])

        msgs = types.SimpleNamespace(create=create)
        fake = mock.Mock(return_value=types.SimpleNamespace(messages=msgs, beta=types.SimpleNamespace(messages=msgs)))
        fixed = [{"start": 30.0, "end": 60.0, "note": "catatan", "ref": "timeline"},
                 {"start": 200.0, "end": 230.0, "note": "", "ref": "link"}]
        with mock.patch("anthropic.Anthropic", fake):
            clips, _ = core.find_highlights_ai(segs, "k", 2, 20, 60, "claude-sonnet-5-5", "t", brief={
                "instructions": "fokus bisnis", "examples": ["contoh"], "fixed": fixed,
                "points": [{"t": 120.0, "note": "lucu"}]})
        prompt = captured["messages"][0]["content"]
        self.assertIn("<instruksi>\nfokus bisnis\n</instruksi>", prompt)
        self.assertIn("#1 [30.0-60.0] catatan pengguna: catatan", prompt)
        self.assertIn("detik 120.0 (lucu)", prompt)
        t1 = next(c for c in clips if c["start"] == 30.0)
        self.assertEqual((t1["title"], t1["ref"], t1["hashtags"]), ("Judul timeline", "timeline", ["#ab", "#c"]))
        self.assertTrue(any(c["start"] == 200.0 and c["ref"] == "link" for c in clips))  # AI lupa -> tetap dibuat
        self.assertFalse(any(c["title"] == "Tumpang tindih" for c in clips))
        self.assertTrue(any(c["title"] == "Baru" and c["ref"] == "titik" for c in clips))


if __name__ == "__main__":
    unittest.main()
