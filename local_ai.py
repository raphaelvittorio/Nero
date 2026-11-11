"""
Nero - AI lokal gratis, berjalan di komputer pengguna (tanpa API key, tanpa biaya).

Didukung:
  - Ollama (https://ollama.com), alamat bawaan http://127.0.0.1:11434
  - server lain yang meniru API OpenAI, mis. LM Studio (http://127.0.0.1:1234), llama.cpp, Jan

Dipakai bersama semua fitur. Alamat server & model tersimpan di pengaturan umum Nero
(local_ai_url, local_ai_model). Semua permintaan hanya ke alamat itu (biasanya komputer ini sendiri).
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time

import requests

DEFAULT_URL = "http://127.0.0.1:11434"

# Model yang bisa melihat gambar, urut dari yang paling disarankan untuk laptop biasa.
# Ukuran perkiraan unduhan (GB). Dipakai versi "instruct": tag qwen3-vl tanpa akhiran adalah versi
# "thinking" yang selalu berpikir panjang dulu (ribuan token, beberapa menit per clip) walau diminta tidak.
RECOMMENDED = [
    {"name": "qwen3-vl:4b-instruct", "size_gb": 3.3,
     "label": "Qwen3-VL 4B: paling seimbang, cocok untuk GPU 4-6 GB (disarankan)"},
    {"name": "qwen3-vl:2b-instruct", "size_gb": 1.9,
     "label": "Qwen3-VL 2B: paling ringan & cepat, muat penuh di GPU 4 GB atau tanpa GPU"},
    {"name": "qwen3-vl:8b-instruct", "size_gb": 6.1,
     "label": "Qwen3-VL 8B: paling teliti, butuh GPU 8 GB atau lebih"},
    {"name": "gemma3:4b", "size_gb": 3.3,
     "label": "Gemma 3 4B: alternatif dari Google"},
]
THINK_LIMIT = 150  # potongan "berpikir" sebelum dihentikan: model yang tidak bisa berhenti berpikir terlalu lambat
# Nama model yang biasanya bisa melihat gambar (dipakai bila server tidak melaporkan kemampuannya).
_VISION_HINT = re.compile(r"(vl|vision|llava|bakllava|moondream|minicpm-v|gemma3|gemma-3|pixtral|"
                          r"mistral-small3\.[12]|llama4|granite3\.2-vision|internvl|smolvlm|phi-?4-mm)", re.I)


class LocalAIError(RuntimeError):
    """Galat yang pesannya aman & jelas untuk ditampilkan ke pengguna."""


def clean_url(url: str | None) -> str:
    url = (url or "").strip().rstrip("/") or DEFAULT_URL
    if not re.match(r"^https?://", url):
        url = "http://" + url
    return re.sub(r"/(v1|api)$", "", url)


def _err(e: Exception, url: str) -> LocalAIError:
    if isinstance(e, LocalAIError):
        return e
    if isinstance(e, requests.ConnectionError):
        return LocalAIError(f"AI lokal belum berjalan di {url}. Buka aplikasi Ollama dulu "
                            "(atau pasang dari ollama.com), lalu coba lagi.")
    if isinstance(e, requests.Timeout):
        return LocalAIError("AI lokal terlalu lama menjawab. Coba model yang lebih kecil di Pengaturan Nero.")
    return LocalAIError(f"AI lokal gagal: {e}"[:300])


def _http_error(r: requests.Response, model: str = "") -> LocalAIError:
    try:
        msg = r.json().get("error") or r.text
        if isinstance(msg, dict):
            msg = msg.get("message") or json.dumps(msg)
    except Exception:
        msg = r.text
    msg = str(msg)[:300]
    if r.status_code == 404 or "not found" in msg.lower():
        return LocalAIError(f"Model '{model}' belum diunduh. Unduh dulu di Pengaturan Nero → AI lokal.")
    if "memory" in msg.lower():
        return LocalAIError("Memori GPU/RAM tidak cukup untuk model ini. Pilih model yang lebih kecil "
                            f"(mis. qwen3-vl:2b-instruct). ({msg})")
    return LocalAIError(f"AI lokal menolak permintaan ({r.status_code}): {msg}")


# --------------------------------------------------------------------------
# Status: server jenis apa, model apa saja yang ada
# --------------------------------------------------------------------------
_caps_cache: dict[tuple, tuple[bool, bool]] = {}


def _ollama_caps(url: str, name: str, digest: str) -> tuple[bool, bool]:
    """(bisa melihat gambar, model 'berpikir' dulu sebelum menjawab)."""
    key = (url, name, digest)
    if key not in _caps_cache:
        vision = bool(_VISION_HINT.search(name))
        thinking = "thinking" in name
        try:
            r = requests.post(f"{url}/api/show", json={"model": name}, timeout=4)
            if r.ok:
                caps = r.json().get("capabilities")
                if isinstance(caps, list):
                    vision, thinking = "vision" in caps, "thinking" in caps
        except requests.RequestException:
            pass
        _caps_cache[key] = (vision, thinking)
    return _caps_cache[key]


def status(url: str | None = None) -> dict:
    """{ok, kind: 'ollama'|'openai'|None, url, models:[{name, vision, size_gb}], error}"""
    url = clean_url(url)
    try:
        r = requests.get(f"{url}/api/tags", timeout=3)
        if r.ok and "models" in r.json():
            models = []
            for m in r.json()["models"]:
                name = m.get("name") or m.get("model") or ""
                vision, thinking = _ollama_caps(url, name, m.get("digest", ""))
                models.append({"name": name, "size_gb": round((m.get("size") or 0) / 1e9, 1),
                               "vision": vision, "thinking": thinking})
            return {"ok": True, "kind": "ollama", "url": url, "models": models, "error": ""}
    except (requests.RequestException, ValueError):
        pass
    try:
        r = requests.get(f"{url}/v1/models", timeout=3)
        if r.ok:
            data = r.json().get("data") or []
            models = [{"name": m.get("id", ""), "size_gb": 0, "vision": bool(_VISION_HINT.search(m.get("id", ""))),
                       "thinking": "thinking" in m.get("id", "")} for m in data if m.get("id")]
            return {"ok": True, "kind": "openai", "url": url, "models": models, "error": ""}
    except (requests.RequestException, ValueError):
        pass
    return {"ok": False, "kind": None, "url": url, "models": [],
            "error": f"AI lokal tidak ditemukan di {url}. Pasang & buka Ollama (gratis, ollama.com)."}


def pick_model(st: dict, wanted: str | None) -> str | None:
    """Model yang dipakai: pilihan pengguna bila ada di server, selain itu model vision pertama
    (urut sesuai daftar yang disarankan)."""
    names = [m["name"] for m in st.get("models", [])]
    if wanted and (wanted in names or f"{wanted}:latest" in names or st.get("kind") == "openai"):
        return wanted
    vision = [m for m in st.get("models", []) if m.get("vision")]
    # model yang langsung menjawab didahulukan; model "berpikir" hanya bila tidak ada pilihan lain
    vision.sort(key=lambda m: bool(m.get("thinking")))
    for rec in RECOMMENDED:
        if any(m["name"] == rec["name"] for m in vision):
            return rec["name"]
    return vision[0]["name"] if vision else None


# --------------------------------------------------------------------------
# Unduh model (khusus Ollama)
# --------------------------------------------------------------------------
class PullJob:
    """Unduhan model di latar belakang, bisa dipantau & dibatalkan dari halaman."""

    def __init__(self, url: str, model: str):
        self.url, self.model = clean_url(url), model
        self.status, self.progress, self.stage, self.error = "proses", 0.0, "Menghubungi Ollama...", ""
        self.cancelled = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        parts: dict[str, tuple[int, int]] = {}   # model terdiri dari beberapa berkas: digest -> (selesai, total)
        try:
            with requests.post(f"{self.url}/api/pull", json={"model": self.model, "stream": True},
                               stream=True, timeout=(5, 120)) as r:
                if not r.ok:
                    raise _http_error(r, self.model)
                for line in r.iter_lines():
                    if self.cancelled:
                        self.status, self.stage = "batal", "Dibatalkan"
                        return
                    if not line:
                        continue
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise LocalAIError(f"Gagal mengunduh {self.model}: {ev['error']}"[:300])
                    total, done = ev.get("total") or 0, ev.get("completed") or 0
                    if total:
                        # progres gabungan semua berkas yang sudah terlihat. Per berkas tidak boleh mundur:
                        # Ollama mengulang potongan yang gagal, sehingga angka "selesai" kadang turun.
                        key = ev.get("digest") or ev.get("status", "")
                        parts[key] = (max(done, parts.get(key, (0, 0))[0]), total)
                        done, total = (sum(x[i] for x in parts.values()) for i in (0, 1))
                        self.progress = done / total
                        self.stage = f"Mengunduh {self.model}: {done / 1e9:.1f} / {total / 1e9:.1f} GB"
                    elif ev.get("status"):
                        self.stage = str(ev["status"])[:120]
            self.status, self.progress, self.stage = "selesai", 1.0, f"{self.model} siap dipakai"
        except Exception as e:
            self.status, self.error = "gagal", str(_err(e, self.url))

    def as_dict(self):
        return {"model": self.model, "status": self.status, "progress": round(self.progress, 3),
                "stage": self.stage, "error": self.error}


# --------------------------------------------------------------------------
# Tanya model: jawaban JSON sesuai skema, boleh disertai gambar
# --------------------------------------------------------------------------
def _parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    # jawaban terpotong (mis. model kecil terus mengulang kalimat sampai batas token): ambil semua isian
    # yang sudah lengkap, supaya pembacaan tidak hilang hanya karena kalimat terakhirnya terpotong
    pairs = re.findall(r'"(\w+)"\s*:\s*("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)', text)
    if len(pairs) >= 3:
        return {k: json.loads(v) for k, v in pairs}
    raise LocalAIError("Jawaban AI lokal bukan JSON yang bisa dibaca. Coba lagi atau pilih model lain.")


def chat_json(prompt: str, schema: dict, images: list[bytes] = (), *, url: str | None = None,
              model: str, system: str = "", timeout: float = 900, alive=None, on_token=None) -> dict:
    """Kirim pertanyaan (+ gambar JPEG/PNG) ke AI lokal, kembalikan jawaban berupa dict.
    alive(): dipanggil berkala, boleh melempar galat untuk membatalkan. on_token(n): jumlah potongan jawaban."""
    url = clean_url(url)
    st = status(url)
    if not st["ok"]:
        raise LocalAIError(st["error"])
    b64 = [base64.b64encode(x).decode("ascii") for x in images]
    try:
        if st["kind"] == "ollama":
            return _ollama_chat(url, model, system, prompt, b64, schema, timeout, alive, on_token)
        return _openai_chat(url, model, system, prompt, b64, schema, timeout)
    except LocalAIError:
        raise
    except Exception as e:
        if alive:
            alive()  # dibatalkan pengguna: teruskan galat pembatalan, bukan galat AI
        raise _err(e, url) from e


def _ollama_chat(url, model, system, prompt, b64, schema, timeout, alive, on_token):
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt, **({"images": b64} if b64 else {})}]
    # konteks secukupnya (gambar sudah diperkecil): memori cache lebih kecil, lebih banyak model muat di GPU.
    # num_predict membatasi jawaban supaya teks yang tak berujung tidak membuat pembacaan macet
    # keep_alive pendek: model dilepas dari memori GPU 1 menit setelah dipakai, supaya transkrip Whisper
    # (juga di GPU) tidak kehabisan memori lalu pindah ke CPU. Membaca beberapa clip berturut tetap cepat
    body = {"model": model, "messages": msgs, "stream": True, "format": schema, "think": False,
            "keep_alive": "60s", "options": {"temperature": 0, "num_ctx": 5120, "num_predict": 700}}
    for attempt in range(2):
        r = requests.post(f"{url}/api/chat", json=body, stream=True, timeout=(5, timeout))
        if r.ok:
            break
        err = _http_error(r, model)
        r.close()
        # model lama / bukan model "berpikir" menolak opsi think: ulangi tanpa opsi itu
        if attempt == 0 and "think" in str(err).lower():
            body.pop("think")
            continue
        raise err
    parts, n, thought, t0 = [], 0, 0, time.time()
    with r:
        for line in r.iter_lines():
            if alive:
                alive()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("error"):
                raise LocalAIError(f"AI lokal gagal: {ev['error']}"[:300])
            if (ev.get("message") or {}).get("thinking"):
                thought += 1
                if thought > THINK_LIMIT:
                    raise LocalAIError(
                        f"Model '{model}' selalu 'berpikir' panjang sebelum menjawab, jadi sangat lambat. "
                        "Unduh versi instruct (mis. qwen3-vl:4b-instruct) di Pengaturan Nero → AI lokal.")
            piece = (ev.get("message") or {}).get("content") or ""
            if piece:
                parts.append(piece)
                n += 1
                if on_token:
                    on_token(n)
            if time.time() - t0 > timeout:
                raise LocalAIError("AI lokal terlalu lama menjawab. Coba model yang lebih kecil.")
            if ev.get("done"):
                break
    return _parse_json("".join(parts))


def _openai_chat(url, model, system, prompt, b64, schema, timeout):
    content = [{"type": "text", "text": prompt}] + \
              [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{x}"}} for x in b64]
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    formats = [{"type": "json_schema", "json_schema": {"name": "jawaban", "strict": True, "schema": schema}},
               {"type": "json_object"}, None]
    last = None
    for fmt in formats:
        body = {"model": model, "messages": msgs, "temperature": 0, "stream": False}
        if fmt:
            body["response_format"] = fmt
        r = requests.post(f"{url}/v1/chat/completions", json=body, timeout=(5, timeout))
        if r.ok:
            text = r.json()["choices"][0]["message"].get("content") or ""
            return _parse_json(text)
        last = _http_error(r, model)
        if r.status_code not in (400, 422):
            break
    raise last
