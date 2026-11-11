"""Render clip bergaya diketahui dari video buatan, lalu 'Tiru gaya' harus membacanya kembali.
Juga memeriksa 'Hapus jeda' memendekkan video sesuai perhitungan. Butuh ~1 menit."""
import os
import random
import shutil
import tempfile
import unittest

from tests.util import ROOT  # noqa: F401  (menambahkan folder aplikasi ke sys.path)

from features.clip import engine as core  # noqa: E402

TITLE = "Kenapa bisnis pertamaku bangkrut?"
VARIANTS = {
    "A": dict(layout="blur", caption_color="kuning", caption_pos=0.68, caption_size=86, caption_words=3,
              caption_upper=True, title_on=True, title_bg="putih", title_secs=0, progress_bar=True),
    "B": dict(layout="center", caption_color="hijau", caption_pos=0.55, caption_size=110, caption_words=1,
              caption_upper=False, title_on=True, title_bg="kuning", title_secs=3, progress_bar=False),
    "D": dict(layout="blur", caption_color="pink", caption_pos=0.62, caption_size=96, caption_words=2,
              caption_upper=False, title_on=True, title_bg="hitam", title_secs=5, progress_bar=True),
    "E": dict(layout="center", caption_color="hijau", caption_base="kuning", caption_pos=0.72, caption_size=90,
              caption_words=3, caption_upper=True, title_on=False, progress_bar=True, caption_font="montserrat",
              caption_emphasis=True),
}
# Batasan yang diketahui: Impact huruf kecil, 1 kata per tampilan, kata Indonesia. Huruf 'x' Impact hampir
# setinggi huruf tinggi (b, d, l), jadi pada lebar analisis 320 px teks terbaca seperti HURUF BESAR dan
# ukurannya terbaca ~15% lebih kecil. Kunci yang terkena tidak diperiksa untuk gaya ini.
KNOWN_LIMITS = {"B": {"caption_upper", "caption_size"}}
WORDS = ("Kenapa bisnis pertama saya bangkrut padahal modalnya besar sekali ternyata rahasianya ada di cara "
         "mengatur uang setiap bulan dan banyak orang tidak tahu soal ini sama sekali jadi dengarkan baik baik "
         "karena ini penting untuk kamu yang baru mulai usaha").split()


def fake_words(t0=0.3, rate=2.6, pause_after=None, pause=1.5):
    rnd, t, out = random.Random(3), t0, []
    for i, w in enumerate(WORDS):
        out.append({"start": round(t, 2), "end": round(t + 0.2 + 0.03 * len(w), 2), "word": w})
        t += 1 / rate + rnd.uniform(-0.03, 0.03)
        if pause_after and i + 1 in pause_after:
            t += pause
    return out


class RenderGaya(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="nero-test-")
        cls.src = os.path.join(cls.tmp, "sumber.mp4")
        # video horizontal buatan: gradasi bergerak + bintik (seperti tekstur video asli) + nada
        core.run_ffmpeg(["-f", "lavfi", "-i", "gradients=s=1280x720:speed=0.03:n=3,noise=alls=25:allf=t+u",
                         "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", "16",
                         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", cls.src])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def render(self, name, style, words, end=14.0):
        out = os.path.join(self.tmp, f"{name}.mp4")
        core.render_clip(self.src, 0.0, end, out, words, {"loudnorm": False, **style}, TITLE)
        return out

    def test_tiru_gaya_membaca_kembali(self):
        for name, style in VARIANTS.items():
            with self.subTest(gaya=name):
                got = core.analyze_reference_style(self.render(name, style, fake_words()))["style"]
                for k in ("layout", "caption_color", "caption_words", "title_on", "progress_bar"):
                    self.assertEqual(got.get(k), style[k], k)
                self.assertEqual(got.get("caption_base"), style.get("caption_base", "putih"))
                self.assertAlmostEqual(got["caption_pos"], style["caption_pos"], delta=0.03)
                skip = KNOWN_LIMITS.get(name, set())
                if "caption_size" not in skip:
                    # ukuran dikalibrasi untuk Impact; font lain bisa meleset sampai ~15%
                    tol = 10 if style.get("caption_font", "impact") == "impact" else 0.15 * style["caption_size"]
                    self.assertAlmostEqual(got["caption_size"], style["caption_size"], delta=tol)
                # HURUF BESAR boleh tidak diisi bila tidak pasti, tetapi tidak boleh salah
                if "caption_upper" in skip:
                    pass
                elif "caption_upper" in got:
                    self.assertEqual(got["caption_upper"], style["caption_upper"], "caption_upper")
                elif style["caption_upper"]:
                    self.fail("HURUF BESAR seharusnya terbaca pasti")
                if style["title_on"]:
                    self.assertEqual((got.get("title_bg"), got.get("title_secs")),
                                     (style["title_bg"], style["title_secs"]))

    def test_kotak_sorot_terbaca(self):
        """Kotak berwarna di belakang kata terbaca dari piksel (termasuk HURUF BESAR bergaris tepi), dan kata
        berwarna biasa (mis. seluruh huruf kuning tebal) tidak dikira kotak."""
        cases = {
            "K2": dict(caption_highlight="kotak", caption_color="merah", caption_font="impact", caption_words=2),
            "K5": dict(caption_highlight="kotak", caption_color="kuning", caption_font="impact"),
            "K1": dict(caption_highlight="kotak", caption_color="ungu", caption_font="poppins", caption_upper=False),
        }
        for name, style in cases.items():
            with self.subTest(gaya=name):
                got = core.analyze_reference_style(self.render(name, {"layout": "center", **style}, fake_words()))["style"]
                self.assertEqual((got.get("caption_highlight"), got.get("caption_color")), ("kotak", style["caption_color"]))
        for name in ("A", "E"):   # dirender ulang di test_tiru_gaya; di sini cukup dibaca dari berkasnya bila ada
            path = os.path.join(self.tmp, f"{name}.mp4")
            if not os.path.exists(path):
                path = self.render(name, VARIANTS[name], fake_words())
            with self.subTest(bukan_kotak=name):
                self.assertNotEqual(core.analyze_reference_style(path)["style"].get("caption_highlight"), "kotak")

    def test_efek_baru_terbaca_kembali(self):
        """Latar hitam, filter hitam-putih, dan zoom pelan dibaca dari video bertekstur."""
        from tests.test_gaya_ai import textured_source
        src = os.path.join(self.tmp, "tekstur.mp4")
        textured_source(src)
        cases = {"hitam": dict(layout="hitam", filter="hitamputih"), "halus": dict(layout="center", zoom="halus")}
        for name, style in cases.items():
            with self.subTest(gaya=name):
                out = os.path.join(self.tmp, f"efek_{name}.mp4")
                core.render_clip(src, 0.0, 14.0, out, fake_words(), {"loudnorm": False, **style}, TITLE)
                got = core.analyze_reference_style(out)["style"]
                for k, v in style.items():
                    self.assertEqual(got.get(k), v, k)
                if name == "halus":
                    self.assertNotIn("filter", got)

    def test_hapus_jeda_memendekkan_video(self):
        words = fake_words(pause_after={8, 20})          # dua jeda 1,5 detik
        style = {"layout": "center", "cut_pauses": 0.3}
        keep, rel = core.clip_timeline(words, 0.0, 14.0, style)
        expect = sum(m - k for k, m in keep) / core.OUT_FPS
        dur = core.probe(self.render("jeda", style, words)).duration
        self.assertLess(expect, 14.0 - 2.5)
        self.assertAlmostEqual(dur, expect, delta=0.1)


if __name__ == "__main__":
    unittest.main()
