"""Platform Nero: pengaturan bersama, daftar fitur, rute, dan pemindahan data ClipMaker versi lama."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.util import ROOT  # noqa: F401  (menambahkan folder aplikasi ke sys.path)

import common  # noqa: E402
from features.clip import api as clip  # noqa: E402


class Sandbox(unittest.TestCase):
    """Folder data/ dan output/ sementara, supaya tidak menyentuh milik pengguna."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nero-test-")
        data, out = os.path.join(self.tmp, "data"), os.path.join(self.tmp, "output")
        os.makedirs(os.path.join(data, "clip", "projects"))
        os.makedirs(os.path.join(out, "clip"))
        self.patches = [
            mock.patch.object(common, "DATA", data),
            mock.patch.object(common, "OUTPUT", out),
            mock.patch.object(common, "SETTINGS_PATH", os.path.join(data, "settings.json")),
            mock.patch.object(clip, "DATA", os.path.join(data, "clip")),
            mock.patch.object(clip, "PROJ", os.path.join(data, "clip", "projects")),
            mock.patch.object(clip, "OUTPUT", os.path.join(out, "clip")),
            mock.patch.dict(common._feature_defaults, {"clip": clip.SETTINGS}, clear=True),
        ]
        for p in self.patches:
            p.start()
        self.data, self.out = data, out

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path, text="x"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


class Pengaturan(Sandbox):
    def test_bawaan_dan_gabungan(self):
        s = common.feature_settings("clip")
        self.assertEqual(s["api_key"], "")
        self.assertEqual(s["n_clips"], 5)
        self.assertEqual(s["style"]["caption_font"], "impact")

    def test_hanya_kunci_dikenal(self):
        common.update_settings({"ai_model": "x", "n_clips": 9, "asing": 1})
        common.update_settings({"n_clips": 7, "api_key": "rahasia", "style": {"caption_size": 70}}, "clip")
        raw = common.read_settings_file()
        self.assertEqual(raw["ai_model"], "x")
        self.assertNotIn("n_clips", raw)  # kunci fitur tidak boleh masuk lewat pengaturan umum
        self.assertNotIn("asing", raw)
        self.assertEqual(raw["clip"]["n_clips"], 7)
        self.assertNotIn("api_key", raw["clip"])  # kunci umum tidak boleh masuk lewat pengaturan fitur
        self.assertEqual(raw["clip"]["style"]["caption_size"], 70)
        self.assertEqual(raw["clip"]["style"]["caption_font"], "impact")  # gaya lain tetap ada

    def test_bagian_fitur_lain_tidak_hilang(self):
        common.write_settings_file({"fitur_lama": {"a": 1}})
        common.update_settings({"ai_model": "y"})
        self.assertEqual(common.read_settings_file()["fitur_lama"], {"a": 1})


class PindahDataLama(Sandbox):
    def legacy(self):
        common.write_settings_file({
            "api_key": "sk-lama", "ai_model": "m", "cookies_browser": "edge",
            "whisper_model": "medium", "n_clips": 3, "style": {"caption_size": 60, "layout": "face"},
        })
        proj = os.path.join(self.data, "projects", "20261109-142038-c374")
        self.write(os.path.join(proj, "project.json"), json.dumps({
            "id": "20261109-142038-c374", "status": "siap",
            "clips": [{"id": "a1", "file": "Video_Saya/Video_Saya_Judul_a1b2.mp4", "render_status": "selesai"}],
        }))
        self.write(os.path.join(self.out, "Video_Saya", "Video_Saya_Judul_a1b2.mp4"))
        self.write(os.path.join(self.data, "style_ref", "abcd", "ref.mp4"))

    def test_pindah_sekali(self):
        self.legacy()
        clip.migrate_legacy()

        raw = common.read_settings_file()
        self.assertEqual(raw["api_key"], "sk-lama")
        self.assertEqual(raw["cookies_browser"], "edge")
        self.assertNotIn("whisper_model", raw)
        self.assertEqual(raw["clip"]["whisper_model"], "medium")
        self.assertEqual(raw["clip"]["style"], {"caption_size": 60, "layout": "face"})
        s = common.feature_settings("clip")
        self.assertEqual(s["style"]["caption_size"], 60)
        self.assertEqual(s["style"]["caption_font"], "impact")

        self.assertFalse(os.path.exists(os.path.join(self.data, "projects")))
        self.assertFalse(os.path.exists(os.path.join(self.data, "style_ref")))
        self.assertTrue(os.path.isfile(os.path.join(clip.PROJ, "20261109-142038-c374", "project.json")))
        # alamat berkas hasil di project.json relatif terhadap output/clip, jadi tetap benar
        self.assertTrue(os.path.isfile(os.path.join(clip.OUTPUT, "Video_Saya", "Video_Saya_Judul_a1b2.mp4")))
        self.assertEqual(sorted(os.listdir(self.out)), ["clip"])
        self.assertFalse(os.path.exists(os.path.join(clip.DATA, ".pindah-hasil")))

        # dijalankan lagi: tidak ada yang berubah, folder fitur lain di output/ tidak tersentuh
        self.write(os.path.join(self.out, "fitur_lain", "hasil.txt"))
        before = common.read_settings_file()
        clip.migrate_legacy()
        self.assertEqual(common.read_settings_file(), before)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "fitur_lain", "hasil.txt")))

    def test_dicoba_lagi_bila_gagal(self):
        self.legacy()
        real = os.replace

        def locked(src, dst):
            if os.path.basename(src) == "Video_Saya":
                raise PermissionError("sedang dibuka")
            return real(src, dst)

        with mock.patch("os.replace", side_effect=locked):
            clip.migrate_legacy()
        self.assertTrue(os.path.isdir(os.path.join(self.out, "Video_Saya")))
        self.assertTrue(os.path.exists(os.path.join(clip.DATA, ".pindah-hasil")))

        clip.migrate_legacy()  # aplikasi dibuka lagi, berkas sudah tidak dibuka
        self.assertTrue(os.path.isdir(os.path.join(clip.OUTPUT, "Video_Saya")))
        self.assertFalse(os.path.exists(os.path.join(clip.DATA, ".pindah-hasil")))

    def test_instal_baru_tidak_memindah_apa_pun(self):
        self.write(os.path.join(self.out, "fitur_lain", "hasil.txt"))
        clip.migrate_legacy()
        self.assertTrue(os.path.isfile(os.path.join(self.out, "fitur_lain", "hasil.txt")))
        self.assertEqual(common.read_settings_file(), {})


class Rute(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.c = app.app.test_client()

    def test_fitur_terdaftar(self):
        rules = {r.rule for r in self.app.app.url_map.iter_rules()}
        for rule in ("/api/clip/state", "/api/clip/settings", "/api/clip/media/<pid>/<path:name>",
                     "/api/settings", "/api/overview", "/out/<path:name>"):
            self.assertIn(rule, rules)
        self.assertNotIn("/api/state", rules)

    def test_ringkasan(self):
        r = self.c.get("/api/overview", base_url="http://127.0.0.1:7860")
        self.assertEqual(r.status_code, 200)
        self.assertIn("clip", r.get_json()["features"])

    def test_api_key_tidak_dikirim(self):
        with mock.patch.object(common, "load_settings", return_value={
                **common.GLOBAL_DEFAULTS, "api_key": "sk-rahasia", "clip": clip.SETTINGS}):
            for url in ("/api/settings", "/api/clip/settings"):
                r = self.c.get(url, base_url="http://127.0.0.1:7860")
                self.assertNotIn("sk-rahasia", r.get_data(as_text=True))
                self.assertTrue(r.get_json()["has_key"])

    def test_halaman_tampilan(self):
        local = "http://127.0.0.1:7860"
        self.assertEqual(self.app.web_alias("clip"), "clip.html")
        self.assertEqual(self.app.web_alias("clip/__next.clip.__PAGE__.txt"), "clip/__next.clip/__PAGE__.txt")
        self.assertEqual(self.app.web_alias("__next.__PAGE__.txt"), "__next.__PAGE__.txt")
        if os.path.isfile(os.path.join(common.WEB, "clip.html")):  # web/ hasil build sudah ada
            self.assertEqual(self.c.get("/clip", base_url=local).status_code, 200)
            self.assertEqual(self.c.get("/clip/__next.clip.__PAGE__.txt", base_url=local).status_code, 200)
        self.assertEqual(self.c.get("/api/tidak-ada", base_url=local).status_code, 404)

    def test_host_asing_ditolak(self):
        self.assertEqual(self.c.get("/api/overview", base_url="http://evil.example").status_code, 403)
        r = self.c.post("/api/settings", json={}, base_url="http://127.0.0.1:7860",
                        headers={"Origin": "http://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_ping_dan_pengaturan_desktop(self):
        local = "http://127.0.0.1:7860"
        self.assertEqual(self.c.get("/api/ping", base_url=local).get_json(), {"app": common.APP_NAME})
        self.assertIn("desktop", self.c.get("/api/settings", base_url=local).get_json())

    def test_matikan(self):
        local = "http://127.0.0.1:7860"
        with mock.patch.object(self.app.threading, "Timer") as timer:  # jangan benar-benar keluar
            r = self.c.post("/api/shutdown", base_url=local, headers={"Origin": "http://evil.example"})
            self.assertEqual(r.status_code, 403)
            timer.assert_not_called()
            self.assertEqual(self.c.post("/api/shutdown", base_url=local).status_code, 200)
            timer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
