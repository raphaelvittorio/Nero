"""AI lokal gratis (Ollama palsu, tanpa internet), penggabungan pengukuran + AI, pustaka gaya,
dan pembacaan gaya lengkap dari clip referensi. Butuh ~20 detik (merender satu clip contoh)."""
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import numpy as np

from tests.util import ROOT  # noqa: F401  (menambahkan folder aplikasi ke sys.path)

import common  # noqa: E402
import gemini_ai  # noqa: E402
import local_ai  # noqa: E402
from features.clip import api as clip  # noqa: E402
from features.clip import engine as core  # noqa: E402
from features.clip import style_ai  # noqa: E402
from features.clip.presets import DEFAULT_STYLE, PRESETS  # noqa: E402

AI_ANSWER = {
    "has_subtitles": True, "font_number": "4", "uppercase": True, "words_per_screen": "3",
    "subtitle_position": "lower_middle", "text_color": "white", "highlight_style": "box",
    "highlight_color": "purple", "outline": "thick", "shadow": False, "dark_box": False,
    "title_style": "red_box", "layout": "face_crop", "color_look": "warm", "emoji": True,
    "name": "Podcast Kotak Ungu", "summary": "Subtitle tebal dengan kotak ungu pada kata yang diucapkan.",
}


class FakeOllama(BaseHTTPRequestHandler):
    """Meniru API Ollama secukupnya: /api/tags, /api/show, /api/chat (streaming), /api/pull."""
    answer = AI_ANSWER
    reject_think = False
    log: list = []

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            for ev in events:
                self.wfile.write((json.dumps(ev) + "\n").encode())
        except ConnectionError:  # klien sengaja berhenti di tengah (mis. model yang terus berpikir)
            pass

    def do_GET(self):
        if self.path == "/api/tags":
            return self._json(200, {"models": [{"name": "qwen3-vl:4b", "size": 3.3e9, "digest": "a"},
                                               {"name": "llama3.2:3b", "size": 2e9, "digest": "b"}]})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        FakeOllama.log.append((self.path, body))
        if self.path == "/api/show":
            caps = ["completion", "vision"] if "vl" in body["model"] else ["completion"]
            if "pikir" in body["model"]:
                caps.append("thinking")
            return self._json(200, {"capabilities": caps})
        if self.path == "/api/chat":
            if FakeOllama.reject_think and "think" in body:
                return self._json(400, {"error": f'"{body["model"]}" does not support thinking'})
            if body["model"] == "hilang:1b":
                return self._json(404, {"error": "model 'hilang:1b' not found"})
            if "pikir" in body["model"]:  # seperti qwen3-vl versi thinking: tetap berpikir walau think=false
                return self._stream([{"message": {"thinking": "hmm "}, "done": False}] * 400 + [{"done": True}])
            text = json.dumps(self.answer)
            k = len(text) // 3
            return self._stream([{"message": {"content": text[:k]}, "done": False},
                                 {"message": {"content": text[k:2 * k]}, "done": False},
                                 {"message": {"content": text[2 * k:]}, "done": False}, {"done": True}])
        if self.path == "/api/pull":
            return self._stream([{"status": "pulling manifest"}, {"status": "pulling", "total": 100, "completed": 40},
                                 {"status": "pulling", "total": 100, "completed": 100}, {"status": "success"}])
        if self.path == "/v1beta/interactions":   # Gemini (Interactions API)
            FakeOllama.headers_log.append(dict(self.headers))
            key = self.headers.get("x-goog-api-key")
            if key == "habis":
                return self._json(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}})
            if key != "kunci-uji":
                return self._json(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                  "message": "API key not valid. Please pass a valid API key."}})
            text = json.dumps(GEMINI_ANSWER) if body.get("response_format") else "ok"
            return self._json(200, {"status": "completed", "steps": [
                {"type": "thought", "signature": "x"},
                {"type": "model_output", "content": [{"type": "text", "text": text}]}]})
        self._json(404, {"error": "not found"})


GEMINI_ANSWER = {**AI_ANSWER, "font_number": "2", "highlight_style": "color", "highlight_color": "green",
                 "subtitle_animation": "bounce", "zoom": "punch", "name": "Hijau Memantul",
                 "summary": "Dibaca Gemini dari videonya."}


class WithOllama(unittest.TestCase):
    """Server palsu yang menjawab seperti Ollama dan Gemini (tanpa internet)."""

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls._gemini = mock.patch.object(gemini_ai, "API_URL", f"{cls.url}/v1beta")
        cls._gemini.start()

    @classmethod
    def tearDownClass(cls):
        cls._gemini.stop()
        cls.srv.shutdown()

    def setUp(self):
        FakeOllama.log, FakeOllama.reject_think, FakeOllama.headers_log = [], False, []


class Gemini(WithOllama):
    def test_permintaan_video_gambar_skema(self):
        got = gemini_ai.chat_json("tanya", {"type": "object"}, key="kunci-uji", model="gemini-3.8-flash",
                                  images=[b"\xff\xd8gambar"], video=b"\x00\x00video", video_fps=4, system="sys")
        self.assertEqual(got, GEMINI_ANSWER)
        body = [b for p, b in FakeOllama.log if p == "/v1beta/interactions"][-1]
        self.assertEqual(body["model"], "gemini-3.8-flash")
        self.assertEqual([x["type"] for x in body["input"]], ["text", "video", "image", "text"])
        self.assertEqual(body["input"][1]["processing"], {"type": "static", "fps": 4})
        self.assertEqual(body["response_format"]["schema"], {"type": "object"})
        self.assertEqual(body["response_format"]["mime_type"], "application/json")
        h = FakeOllama.headers_log[-1]
        self.assertEqual(h.get("x-goog-api-key"), "kunci-uji")
        self.assertTrue(h.get("Api-Revision"))

    def test_galat_jelas(self):
        with self.assertRaises(local_ai.LocalAIError) as e:
            gemini_ai.chat_json("x", {}, key="habis")
        self.assertIn("Batas pemakaian gratis", str(e.exception))
        self.assertIn("tidak valid", gemini_ai.check("salah")["error"])
        self.assertEqual(gemini_ai.check("kunci-uji"), {"ok": True, "error": ""})
        with self.assertRaises(local_ai.LocalAIError):
            gemini_ai.chat_json("x", {}, key="")


class LocalAI(WithOllama):
    def test_status_dan_pilih_model(self):
        st = local_ai.status(self.url)
        self.assertTrue(st["ok"])
        self.assertEqual(st["kind"], "ollama")
        vision = {m["name"]: m["vision"] for m in st["models"]}
        self.assertEqual(vision, {"qwen3-vl:4b": True, "llama3.2:3b": False})
        self.assertEqual(local_ai.pick_model(st, ""), "qwen3-vl:4b")
        self.assertEqual(local_ai.pick_model(st, "llama3.2:3b"), "llama3.2:3b")   # pilihan pengguna dihormati
        self.assertEqual(local_ai.pick_model(st, "tidak-ada:1b"), "qwen3-vl:4b")

    def test_tidak_berjalan(self):
        st = local_ai.status("http://127.0.0.1:9")
        self.assertFalse(st["ok"])
        self.assertIn("Ollama", st["error"])
        with self.assertRaises(local_ai.LocalAIError):
            local_ai.chat_json("x", {}, url="http://127.0.0.1:9", model="m")

    def test_chat_json_dengan_gambar(self):
        tokens = []
        got = local_ai.chat_json("halo", {"type": "object"}, [b"\xff\xd8gambar"], url=self.url,
                                 model="qwen3-vl:4b", system="sys", on_token=tokens.append)
        self.assertEqual(got, AI_ANSWER)
        self.assertEqual(tokens, [1, 2, 3])
        body = [b for p, b in FakeOllama.log if p == "/api/chat"][-1]
        self.assertEqual(body["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(len(body["messages"][1]["images"]), 1)
        self.assertEqual(body["format"], {"type": "object"})
        self.assertFalse(body["think"])

    def test_model_lama_menolak_think(self):
        FakeOllama.reject_think = True
        self.assertEqual(local_ai.chat_json("x", {}, url=self.url, model="qwen3-vl:4b"), AI_ANSWER)
        chats = [b for p, b in FakeOllama.log if p == "/api/chat"]
        self.assertEqual(len(chats), 2)
        self.assertNotIn("think", chats[1])

    def test_model_yang_selalu_berpikir(self):
        with self.assertRaises(local_ai.LocalAIError) as e:
            local_ai.chat_json("x", {}, url=self.url, model="qwen3-vl:pikir")
        self.assertIn("instruct", str(e.exception))
        # tanpa pilihan pengguna, model yang langsung menjawab didahulukan
        st = {"ok": True, "kind": "ollama", "models": [
            {"name": "qwen3-vl:4b", "vision": True, "thinking": True},
            {"name": "llava:7b", "vision": True, "thinking": False}]}
        self.assertEqual(local_ai.pick_model(st, ""), "llava:7b")
        st["models"].append({"name": "qwen3-vl:4b-instruct", "vision": True, "thinking": False})
        self.assertEqual(local_ai.pick_model(st, ""), "qwen3-vl:4b-instruct")

    def test_model_belum_diunduh(self):
        with self.assertRaises(local_ai.LocalAIError) as e:
            local_ai.chat_json("x", {}, url=self.url, model="hilang:1b")
        self.assertIn("belum diunduh", str(e.exception))

    def test_unduh_model(self):
        job = local_ai.PullJob(self.url, "qwen3-vl:2b")
        for _ in range(100):
            if job.status != "proses":
                break
            time.sleep(0.02)
        self.assertEqual(job.status, "selesai", job.error)
        self.assertEqual(job.progress, 1.0)

    def test_baca_json_berantakan(self):
        self.assertEqual(local_ai._parse_json('<think>hmm</think>```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(local_ai._parse_json('Jawaban: {"a": 2} selesai'), {"a": 2})


class Gabung(unittest.TestCase):
    fonts = style_ai.FONT_ORDER

    def test_pengukuran_didahulukan(self):
        measured = {"captions": True, "caption_size": 90, "caption_pos": 0.7, "caption_words": 2,
                    "caption_color": "putih", "caption_base": "putih", "title_on": True, "layout": "blur"}
        style, src = style_ai.merge(measured, AI_ANSWER, {"color": {"sat": 80, "warm": 34}}, self.fonts)
        self.assertEqual(style["caption_size"], 90)         # angka terukur tidak ditimpa AI
        self.assertEqual(style["caption_words"], 2)
        self.assertEqual(style["layout"], "blur")
        self.assertEqual(style["caption_font"], "montserrat")   # baris 4 lembar font
        self.assertEqual(style["caption_highlight"], "kotak")
        self.assertEqual(style["caption_color"], "ungu")        # warna kotak dari AI
        self.assertEqual(style["caption_stroke"], 3)
        self.assertEqual(style["title_bg"], "merah")
        self.assertEqual(style["filter"], "hangat")             # didukung angka warna (warm 34)
        self.assertEqual(src["caption_size"], "ukur")
        self.assertEqual(src["caption_font"], "ai")

    def test_tebakan_warna_ditolak_bila_angka_tidak_mendukung(self):
        style, _ = style_ai.merge({"captions": True}, AI_ANSWER, {"color": {"sat": 80, "warm": -5}}, self.fonts)
        self.assertNotIn("filter", style)

    def test_subtitle_hanya_terlihat_ai(self):
        style, src = style_ai.merge({"title_on": False, "layout": "face"}, AI_ANSWER, {}, self.fonts)
        self.assertTrue(style["captions"])
        self.assertEqual(style["caption_pos"], 0.62)
        self.assertEqual(style["caption_words"], 3)
        self.assertEqual(src["captions"], "ai")

    def test_tanpa_ai(self):
        style, src = style_ai.merge({"captions": True}, None, {}, self.fonts)
        self.assertEqual(style, {"captions": True})


def textured_source(path, secs=16):
    """Video horizontal bertekstur (bentuk acak diam) supaya gerak kamera/zoom bisa diukur."""
    import cv2
    rng = np.random.default_rng(5)
    img = np.full((720, 1280, 3), 90, np.uint8)
    for _ in range(260):
        c = tuple(int(x) for x in rng.integers(0, 255, 3))
        x, y = int(rng.integers(0, 1280)), int(rng.integers(0, 720))
        if rng.random() < 0.5:
            cv2.circle(img, (x, y), int(rng.integers(8, 60)), c, -1)
        else:
            cv2.rectangle(img, (x, y), (x + int(rng.integers(10, 90)), y + int(rng.integers(10, 90))), c, -1)
    png = path + ".png"
    cv2.imwrite(png, img)
    core.run_ffmpeg(["-loop", "1", "-i", png, "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000",
                     "-t", str(secs), "-r", "30", "-vf", "noise=alls=6:allf=t", "-c:v", "libx264", "-preset",
                     "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", path])


class PustakaGaya(WithOllama):
    """Rute /api/clip/styles* dan /style-jobs dengan folder data sementara."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests.test_render_gaya import TITLE, fake_words
        cls.media = tempfile.mkdtemp(prefix="nero-test-media-")
        src = os.path.join(cls.media, "sumber.mp4")
        textured_source(src)
        cls.ref = os.path.join(cls.media, "referensi.mp4")
        core.render_clip(src, 0.0, 12.0, cls.ref, fake_words(),
                         {**DEFAULT_STYLE, "loudnorm": False, "layout": "center", "caption_color": "hijau",
                          "zoom": "hentak", "title_bg": "kuning"}, TITLE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.media, ignore_errors=True)

    def setUp(self):
        super().setUp()
        import app as server
        self.tmp = tempfile.mkdtemp(prefix="nero-test-")
        data = os.path.join(self.tmp, "data")
        os.makedirs(os.path.join(data, "clip", "projects"))
        self.patches = [
            mock.patch.object(common, "DATA", data),
            mock.patch.object(common, "SETTINGS_PATH", os.path.join(data, "settings.json")),
            mock.patch.object(clip, "DATA", os.path.join(data, "clip")),
            mock.patch.object(clip, "PROJ", os.path.join(data, "clip", "projects")),
            mock.patch.object(clip, "STYLES_PATH", os.path.join(data, "clip", "styles.json")),
            mock.patch.object(clip, "THUMBS", os.path.join(data, "clip", "thumbs")),
            mock.patch.dict(clip.projects, {}, clear=True),
        ]
        for p in self.patches:
            p.start()
        common.update_settings({"local_ai_url": self.url})
        self.c = server.app.test_client()
        self.base = "http://127.0.0.1"

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        r = self.c.get(path, base_url=self.base)
        self.assertEqual(r.status_code, 200, r.data[:300])
        return r.get_json()

    def post(self, path, body=None, code=200, **kw):
        r = self.c.post(path, json=body, base_url=self.base, **kw) if body is not None or not kw else \
            self.c.post(path, base_url=self.base, **kw)
        self.assertEqual(r.status_code, code, r.data[:300])
        return r.get_json()

    def test_simpan_pakai_ubah_hapus(self):
        lst = self.get("/api/clip/styles")
        self.assertEqual(len(lst["presets"]), len(PRESETS))
        self.assertEqual(lst["styles"], [])
        # pakai preset: gaya aktif berubah, watermark milik pengguna tetap
        self.post("/api/clip/settings", {"style": {"handle": "@saya"}})
        self.post("/api/clip/styles/preset:kotak-ungu/apply", {})
        s = self.get("/api/clip/settings")
        self.assertEqual(s["style"]["caption_highlight"], "kotak")
        self.assertEqual(s["style"]["handle"], "@saya")
        self.assertEqual(s["active_style_id"], "preset:kotak-ungu")
        self.assertFalse(self.get("/api/clip/styles")["active_modified"])
        self.post("/api/clip/settings", {"style": {"caption_size": 100}})
        self.assertTrue(self.get("/api/clip/styles")["active_modified"])
        # simpan gaya aktif ke Gaya saya, ganti nama, hapus
        sid = self.post("/api/clip/styles", {"name": "Punyaku"})["style"]["id"]
        mine = self.get("/api/clip/styles")["styles"]
        self.assertEqual([x["name"] for x in mine], ["Punyaku"])
        self.assertNotIn("handle", mine[0]["style"])          # pengaturan pribadi tidak ikut disimpan
        self.assertEqual(mine[0]["style"]["caption_size"], 100)
        self.post(f"/api/clip/styles/{sid}", {"name": "  Baru   sekali "})
        self.assertEqual(self.get("/api/clip/styles")["styles"][0]["name"], "Baru sekali")
        self.c.delete(f"/api/clip/styles/{sid}", base_url=self.base)
        self.assertEqual(self.get("/api/clip/styles")["styles"], [])
        self.assertEqual(self.get("/api/clip/settings")["active_style_id"], "")

    def test_gambar_gaya(self):
        r = self.c.get("/api/clip/styles/preset:neon-pink/thumb", base_url=self.base)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:2], b"\xff\xd8")             # JPEG
        r.close()
        self.assertEqual(self.c.get("/api/clip/styles/tidakada/thumb", base_url=self.base).status_code, 404)

    def test_gaya_per_proyek(self):
        p = clip.new_project(title="Video", style_id="preset:berita")
        self.assertEqual(p["style_id"], "preset:berita")
        s = clip.load_settings()
        self.assertEqual(clip.project_style(p, s)["caption_font"], "georgia")
        self.post(f"/api/clip/project/{p['id']}/style", {"style_id": None})
        self.assertEqual(clip.project_style(p, s)["caption_font"], s["style"]["caption_font"])
        self.post(f"/api/clip/project/{p['id']}/style", {"style_id": "tidakada"}, code=404)
        self.assertIsNone(clip.new_project(title="x", style_id="tidakada")["style_id"])

    def wait_job(self, jid):
        for _ in range(600):
            job = self.get(f"/api/clip/style-jobs/{jid}")
            if job["status"] != "proses":
                return job
            time.sleep(0.1)
        self.fail("pembacaan gaya tidak selesai")

    def test_baca_gaya_dengan_ai_lokal(self):
        with open(self.ref, "rb") as f:
            jid = self.post("/api/clip/style-jobs", content_type="multipart/form-data",
                            data={"file": (io.BytesIO(f.read()), "contoh.mp4")})["id"]
        job = self.wait_job(jid)
        self.assertEqual(job["status"], "selesai", job.get("error"))
        res = job["result"]
        st = res["style"]
        self.assertEqual(res["ai"]["model"], "qwen3-vl:4b")
        self.assertEqual(res["name"], "Podcast Kotak Ungu")
        self.assertEqual(st["zoom"], "hentak")                 # terukur dari gerak frame
        self.assertEqual(st["caption_highlight"], "kotak")     # dari AI
        self.assertEqual(res["sources"]["zoom"], "ukur")
        self.assertEqual(res["sources"]["caption_font"], "ai")
        chat = [b for p, b in FakeOllama.log if p == "/api/chat"][-1]
        self.assertGreaterEqual(len(chat["messages"][-1]["images"]), 3)   # frame + potongan subtitle + lembar font
        # otomatis masuk Gaya saya
        mine = self.get("/api/clip/styles")["styles"]
        self.assertEqual(mine[0]["id"], res["style_id"])
        self.assertEqual(mine[0]["source"]["kind"], "referensi")
        self.assertTrue(mine[0]["summary"])

    def read_ref(self):
        with open(self.ref, "rb") as f:
            jid = self.post("/api/clip/style-jobs", content_type="multipart/form-data",
                            data={"file": (io.BytesIO(f.read()), "contoh.mp4")})["id"]
        job = self.wait_job(jid)
        self.assertEqual(job["status"], "selesai", job.get("error"))
        return job["result"]

    def test_baca_gaya_dengan_gemini(self):
        self.post("/api/settings", {"ai_provider": "gemini", "gemini_key": "kunci-uji"})
        res = self.read_ref()
        self.assertEqual(res["ai"]["provider"], "gemini")
        self.assertEqual(res["ai"]["model"], "gemini-3.8-flash")
        self.assertEqual(res["name"], "Hijau Memantul")
        self.assertEqual(res["style"]["caption_anim"], "bounce")     # hanya terlihat dengan menonton video
        self.assertEqual(res["sources"]["caption_anim"], "ai")
        self.assertEqual(res["style"]["zoom"], "hentak")             # terukur dari piksel tetap didahulukan
        self.assertEqual(res["style"]["caption_font"], "anton")      # baris 2 lembar font
        body = [b for p, b in FakeOllama.log if p == "/v1beta/interactions"][-1]
        self.assertIn("video", [x["type"] for x in body["input"]])
        self.assertIn("subtitle_animation", body["response_format"]["schema"]["properties"])
        self.assertFalse([p for p, _ in FakeOllama.log if p == "/api/chat"])   # AI lokal tidak dipakai

    def test_gemini_habis_pindah_ke_ai_lokal(self):
        self.post("/api/settings", {"ai_provider": "gemini", "gemini_key": "habis"})
        res = self.read_ref()
        self.assertEqual(res["ai"]["provider"], "lokal")
        self.assertTrue(any("Batas pemakaian gratis" in n for n in res["notes"]))

    def test_kunci_tidak_dikirim_ke_halaman(self):
        self.post("/api/settings", {"gemini_key": "kunci-uji", "local_ai_key": "rahasia2", "api_key": "rahasia3"})
        s = self.get("/api/settings")
        self.assertTrue(s["has_gemini_key"] and s["has_local_ai_key"] and s["has_key"])
        dump = json.dumps([s, self.get("/api/local-ai"), self.get("/api/clip/settings")])
        for secret in ("kunci-uji", "rahasia2", "rahasia3"):
            self.assertNotIn(secret, dump)
        self.assertTrue(self.post("/api/gemini/check", {})["ok"])
        self.post("/api/settings", {"clear_gemini_key": True})
        self.assertFalse(self.get("/api/settings")["has_gemini_key"])

    def test_baca_gaya_tanpa_ai(self):
        common.update_settings({"local_ai_url": "http://127.0.0.1:9"})
        with open(self.ref, "rb") as f:
            jid = self.post("/api/clip/style-jobs", content_type="multipart/form-data",
                            data={"file": (io.BytesIO(f.read()), "contoh.mp4")})["id"]
        job = self.wait_job(jid)
        self.assertEqual(job["status"], "selesai", job.get("error"))
        self.assertIsNone(job["result"]["ai"])
        self.assertTrue(job["result"].get("ai_missing"))
        self.assertEqual(job["result"]["style"]["caption_color"], "hijau")
        self.assertEqual(self.get("/api/clip/styles")["styles"][0]["name"], "contoh")

    def test_link_tidak_valid(self):
        self.post("/api/clip/style-jobs", {"url": "bukan link"}, code=400)


if __name__ == "__main__":
    unittest.main()
