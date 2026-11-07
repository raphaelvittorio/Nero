"""
ClipMaker - mesin pembuat clip pendek dari video panjang.

Alur:
  1. download_video()   : unduh dari link (yt-dlp) atau pakai file lokal
  2. extract_audio()    : ambil audio 16 kHz mono untuk transkrip & analisis suara
  3. transcribe()       : transkrip per kata (faster-whisper, berjalan offline)
  4. find_highlights()  : cari momen menarik (heuristik lokal, atau AI Claude bila ada API key)
  5. render_clip()      : potong, crop 9:16 mengikuti wajah, subtitle animasi,
                          judul/hook, progress bar, watermark -> MP4 siap upload
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass

import numpy as np

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30

# --------------------------------------------------------------------------
# FFmpeg
# --------------------------------------------------------------------------
_FFMPEG = None
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def ffmpeg_exe() -> str:
    """Pakai ffmpeg sistem bila ada, kalau tidak pakai bawaan imageio-ffmpeg."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    local = os.path.join(APP_DIR, "tools", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if os.path.isfile(local):
        _FFMPEG = local
        return _FFMPEG
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG = found
        return _FFMPEG
    try:
        import imageio_ffmpeg
        src = imageio_ffmpeg.get_ffmpeg_exe()
        os.makedirs(os.path.dirname(local), exist_ok=True)
        try:
            shutil.copy(src, local)  # beri nama "ffmpeg" agar yt-dlp mengenalinya
            _FFMPEG = local
        except OSError:
            _FFMPEG = src
        return _FFMPEG
    except Exception as e:  # pragma: no cover
        raise RuntimeError("FFmpeg tidak ditemukan. Jalankan install.bat lagi.") from e


def _popen_kwargs():
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kw


def run_ffmpeg(args: list[str]) -> None:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"] + args
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kwargs())
    if r.returncode != 0:
        raise RuntimeError("FFmpeg gagal: " + r.stderr.decode("utf-8", "ignore")[-800:])


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


def probe(path: str) -> VideoInfo:
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kwargs())
    txt = r.stderr.decode("utf-8", "ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    vline = next((l for l in txt.splitlines() if "Video:" in l), "")
    m = re.search(r"\s(\d{2,5})x(\d{2,5})[\s,\[]", vline)
    if not m:
        raise RuntimeError("Tidak bisa membaca ukuran video: " + path)
    w, h = int(m.group(1)), int(m.group(2))
    # video HP yang direkam vertikal kadang disimpan dengan metadata rotasi
    if re.search(r"rotate\s*:\s*-?(90|270)", txt) or "rotation of -90" in txt or "rotation of 90" in txt:
        w, h = h, w
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", vline)
    fps = float(m.group(1)) if m else 30.0
    has_audio = any("Audio:" in l for l in txt.splitlines())
    return VideoInfo(w, h, fps, dur, has_audio)


# --------------------------------------------------------------------------
# 1. Unduh video
# --------------------------------------------------------------------------
def download_video(url: str, out_dir: str, progress=None, cookies_browser: str | None = None) -> dict:
    import yt_dlp

    os.makedirs(out_dir, exist_ok=True)

    def hook(d):
        if progress and d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if tot:
                progress(d.get("downloaded_bytes", 0) / tot)

    opts = {
        "outtmpl": os.path.join(out_dir, "source.%(ext)s"),
        # utamakan H.264 (paling kompatibel), maksimal 1080p
        "format": ("bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/"
                   "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"),
        "merge_output_format": "mp4",
        "ffmpeg_location": os.path.dirname(ffmpeg_exe()),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "retries": 5,
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    if not os.path.exists(path):
        base = os.path.splitext(path)[0]
        for ext in (".mp4", ".mkv", ".webm", ".mov"):
            if os.path.exists(base + ext):
                path = base + ext
                break
    return {
        "path": path,
        "title": info.get("title") or "Video",
        "uploader": info.get("uploader") or "",
        "duration": info.get("duration") or 0,
    }


# --------------------------------------------------------------------------
# 2. Audio
# --------------------------------------------------------------------------
def extract_audio(src: str, wav_path: str) -> None:
    run_ffmpeg(["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav_path])


def audio_energy(wav_path: str, hop: float = 0.5) -> np.ndarray:
    """Energi suara (RMS, dB) per potongan 0,5 detik."""
    with wave.open(wav_path, "rb") as wf:
        sr = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
    n = int(sr * hop)
    if len(data) < n:
        return np.array([-60.0])
    k = len(data) // n
    frames = data[: k * n].reshape(k, n) / 32768.0
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-10)
    return 20 * np.log10(rms + 1e-6)


# --------------------------------------------------------------------------
# 3. Transkrip
# --------------------------------------------------------------------------
_WHISPER = {}
_CUDA_BROKEN = False


def _whisper_model(model_size: str, device: str):
    from faster_whisper import WhisperModel
    key = (model_size, device)
    if key not in _WHISPER:
        compute = "float16" if device == "cuda" else "int8"
        _WHISPER[key] = WhisperModel(model_size, device=device, compute_type=compute)
    return _WHISPER[key]


def transcribe(wav_path: str, model_size: str = "small", language: str | None = None,
               progress=None) -> list[dict]:
    """Hasil: daftar segmen {start, end, text, words:[{start,end,word}]}"""
    global _CUDA_BROKEN
    device = "cpu"
    if not _CUDA_BROKEN:
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                device = "cuda"
        except Exception:
            pass

    # baca WAV sendiri (16 kHz mono) supaya tidak bergantung pada versi PyAV
    with wave.open(wav_path, "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    if device == "cuda":
        try:
            return _transcribe_with(_whisper_model(model_size, "cuda"), audio, language, progress)
        except Exception:
            # Kartu NVIDIA ada, tapi pustaka CUDA (cuBLAS/cuDNN) tidak terpasang -> pakai CPU
            _CUDA_BROKEN = True
            _WHISPER.pop((model_size, "cuda"), None)
    return _transcribe_with(_whisper_model(model_size, "cpu"), audio, language, progress)


def _transcribe_with(model, audio, language, progress) -> list[dict]:
    segments, info = model.transcribe(
        audio,
        language=(language or None) if language != "auto" else None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )
    total = info.duration or 1
    out = []
    for s in segments:
        words = [{"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip()}
                 for w in (s.words or []) if w.word.strip()]
        out.append({"start": round(s.start, 2), "end": round(s.end, 2),
                    "text": s.text.strip(), "words": words})
        if progress:
            progress(min(1.0, s.end / total))
    return out


# --------------------------------------------------------------------------
# 4. Deteksi momen menarik
# --------------------------------------------------------------------------
HOOK_WORDS = [
    # Indonesia
    "rahasia", "ternyata", "jangan", "kenapa", "mengapa", "bagaimana", "gimana", "cara",
    "penting", "harus", "wajib", "gila", "parah", "serius", "jujur", "sebenarnya",
    "sebenernya", "masalah", "kesalahan", "salah", "bahaya", "terbaik", "terburuk",
    "pertama", "uang", "duit", "juta", "miliar", "kaya", "gagal", "sukses", "berhasil",
    "takut", "marah", "sedih", "kaget", "nangis", "ketawa", "lucu", "aneh", "fakta",
    "tips", "trik", "kunci", "intinya", "pokoknya", "bayangkan", "percaya", "bohong",
    "viral", "rugi", "untung", "langsung", "tiba-tiba", "akhirnya", "dulu", "pernah",
    # English
    "secret", "never", "always", "why", "how", "mistake", "truth", "actually", "crazy",
    "insane", "money", "million", "billion", "best", "worst", "first", "important",
    "problem", "story", "shocking", "imagine", "honestly", "literally", "nobody",
]
FILLER = {"eh", "em", "emm", "hmm", "anu", "apa", "gitu", "kayak", "uh", "um", "like", "ya", "yah"}

STOPWORDS = set("""
yang dan di ke dari ini itu dengan untuk pada adalah ada tidak juga saya kita kami kamu
anda dia mereka akan bisa sudah belum lagi aja saja kalau kalo karena jadi atau tapi
tetapi namun bahwa seperti oleh dalam sama apa nya gak nggak enggak ga udah banget
the a an and or but of to in on at for is are was were be been it this that with as
you i we they he she my your our their so just not do does did have has had
kenapa mengapa bagaimana gimana banyak orang padahal coba mulai sangat lebih masih hanya
semua setiap kalau terus ketika maka begitu memang pernah harus akan para sini situ
""".split())


def _fmt(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:04.1f}"


def _words_in(segments, start, end):
    ws = []
    for s in segments:
        if s["end"] < start or s["start"] > end:
            continue
        for w in s["words"]:
            if w["start"] >= start - 0.05 and w["end"] <= end + 0.05:
                ws.append(w)
    return ws


def _make_title(text: str, max_words: int = 9) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    best = None
    for s in sentences[:4]:
        if "?" in s and 3 <= len(s.split()) <= 14:
            best = s
            break
    if best is None:
        best = sentences[0] if sentences else text
    words = best.split()
    t = " ".join(words[:max_words]).strip(" ,.-")
    if len(words) > max_words:
        t += "..."
    return t[:1].upper() + t[1:] if t else "Clip"


def _hashtags(text: str, n: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", text.lower())
    freq = {}
    for w in words:
        if w in STOPWORDS or w in FILLER:
            continue
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda k: -freq[k])[:n]
    return ["#" + w for w in top] + ["#fyp", "#viral"]


def find_highlights_heuristic(segments, energy, n_clips=5, min_len=20, max_len=60) -> list[dict]:
    if not segments:
        return []
    hop = 0.5
    e_mean, e_std = float(np.mean(energy)), float(np.std(energy) + 1e-6)
    cands = []
    for i in range(len(segments)):
        start = segments[i]["start"]
        text_parts, end = [], start
        for j in range(i, len(segments)):
            seg = segments[j]
            if seg["end"] - start > max_len:
                break
            text_parts.append(seg["text"])
            end = seg["end"]
            dur = end - start
            if dur < min_len:
                continue
            ends_clean = seg["text"].rstrip().endswith((".", "!", "?"))
            text = " ".join(text_parts)
            words = [w.lower().strip(".,!?\"'") for w in text.split()]
            nw = max(1, len(words))
            first = segments[i]["text"].lower()

            hook = sum(1 for k in HOOK_WORDS if k in first) * 1.5
            hook += 2.0 if "?" in segments[i]["text"] else 0
            hook += 1.0 if re.search(r"\d", segments[i]["text"]) else 0
            kw = sum(1 for w in words if w in HOOK_WORDS) / nw * 40
            rate = nw / dur  # kata per detik
            rate_score = -abs(rate - 2.8) * 1.2
            filler = sum(1 for w in words if w in FILLER) / nw * -15
            a, b = int(start / hop), max(int(start / hop) + 1, int(end / hop))
            ew = energy[a:b] if a < len(energy) else energy[-1:]
            loud = (float(np.mean(ew)) - e_mean) / e_std * 1.5
            peaks = float(np.mean(ew > e_mean + e_std)) * 3
            silent = float(np.mean(ew < e_mean - 1.5 * e_std)) * -4
            excl = text.count("!") * 0.5 + text.count("?") * 0.4
            clean = 1.5 if ends_clean else -1.0
            length_pref = -abs(dur - (min_len + max_len) / 2) / max_len

            score = hook + kw + rate_score + filler + loud + peaks + silent + excl + clean + length_pref
            cands.append({"start": start, "end": end, "score": score, "text": text,
                          "first": segments[i]["text"], "j": j})
    if not cands:  # video lebih pendek dari durasi minimum
        text = " ".join(s["text"] for s in segments)
        cands = [{"start": segments[0]["start"], "end": segments[-1]["end"], "score": 1.0,
                  "text": text, "first": segments[0]["text"]}]

    cands.sort(key=lambda c: -c["score"])
    chosen = []
    for c in cands:
        if all(c["end"] <= o["start"] + 1 or c["start"] >= o["end"] - 1 for o in chosen):
            chosen.append(c)
        if len(chosen) >= n_clips:
            break

    scores = [c["score"] for c in chosen]
    lo, hi = min(scores), max(scores)
    out = []
    for c in chosen:
        norm = 0.5 if hi == lo else (c["score"] - lo) / (hi - lo)
        viral = int(round(55 + norm * 40))
        reasons = []
        if "?" in c["first"]:
            reasons.append("dibuka dengan pertanyaan")
        if any(k in c["first"].lower() for k in HOOK_WORDS):
            reasons.append("kalimat pembuka kuat")
        if "!" in c["text"]:
            reasons.append("emosi/penekanan tinggi")
        if not reasons:
            reasons.append("bicara padat dan jelas")
        out.append({
            "start": round(c["start"], 2), "end": round(c["end"], 2),
            "title": _make_title(c["first"] if len(c["first"].split()) >= 4 else c["text"]),
            "score": viral, "reason": ", ".join(reasons),
            "caption": _make_title(c["text"], 16),
            "hashtags": _hashtags(c["text"]),
            "text": c["text"],
        })
    out.sort(key=lambda c: c["start"])
    return out


def find_highlights_ai(segments, api_key, n_clips=5, min_len=20, max_len=60,
                       model="claude-sonnet-5-5", video_title="") -> list[dict]:
    """Memakai Claude API untuk memilih momen paling 'viral'."""
    import requests

    lines, total = [], 0
    for s in segments:
        line = f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
        total += len(line)
        if total > 180_000:
            break
        lines.append(line)
    prompt = f"""Kamu adalah editor video pendek (TikTok/Reels/Shorts) yang sangat paham konten viral.
Berikut transkrip video "{video_title}" dengan waktu dalam detik.

{chr(10).join(lines)}

Pilih {n_clips} potongan terbaik untuk dijadikan video pendek. Aturan:
- Durasi tiap potongan {min_len}-{max_len} detik, tidak saling tumpang tindih.
- Mulai tepat di awal kalimat yang langsung menarik perhatian (hook kuat di 3 detik pertama).
- Akhiri di akhir kalimat/gagasan yang tuntas.
- Potongan harus bisa dipahami tanpa menonton video aslinya.
Balas HANYA dengan JSON array, tanpa teks lain, format:
[{{"start": 12.3, "end": 48.9, "title": "judul hook singkat maks 8 kata", "score": 0-100, "reason": "alasan singkat", "caption": "caption postingan 1-2 kalimat", "hashtags": ["#a", "#b"]}}]
Gunakan bahasa yang sama dengan bahasa transkrip."""
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 4000,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Claude API error {r.status_code}: {r.text[:300]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise RuntimeError("Jawaban AI tidak berisi JSON.")
    clips = json.loads(m.group(0))

    starts = [s["start"] for s in segments]
    ends = [s["end"] for s in segments]
    out = []
    for c in clips:
        st, en = float(c["start"]), float(c["end"])
        st = min(starts, key=lambda x: abs(x - st))  # rapikan ke batas kalimat
        en = min(ends, key=lambda x: abs(x - en))
        if en - st < 5:
            continue
        out.append({
            "start": round(st, 2), "end": round(en, 2),
            "title": str(c.get("title", ""))[:90],
            "score": int(c.get("score", 70)),
            "reason": str(c.get("reason", "")),
            "caption": str(c.get("caption", "")),
            "hashtags": [h if h.startswith("#") else "#" + h for h in c.get("hashtags", [])][:8],
            "text": " ".join(s["text"] for s in segments if s["start"] >= st - 0.1 and s["end"] <= en + 0.1),
        })
    out.sort(key=lambda c: c["start"])
    return out


# --------------------------------------------------------------------------
# 5. Render
# --------------------------------------------------------------------------
def _find_font(bold=True) -> str | None:
    cands = []
    if os.name == "nt":
        fd = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        cands += [os.path.join(fd, f) for f in
                  (["impact.ttf", "arialbd.ttf", "seguibl.ttf", "segoeuib.ttf"] if bold else ["arial.ttf"])]
    cands += [os.path.join(APP_DIR, "fonts", "font.ttf"),
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _load_font(size, path=None):
    from PIL import ImageFont
    path = path or _find_font()
    if path:
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _clean_text(t: str) -> str:
    # buang emoji/karakter yang tidak bisa digambar font biasa
    return "".join(ch for ch in t if ord(ch) < 0x2000 or 0x2010 <= ord(ch) <= 0x206F)


def _blend(frame: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    """Tempel gambar RGBA (Pillow) ke frame BGR."""
    h, w = rgba.shape[:2]
    H, W = frame.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[:, :, 3:4].astype(np.float32) / 255.0
    bgr = sub[:, :, 2::-1].astype(np.float32)
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a) + bgr * a).astype(np.uint8)


CAPTION_COLORS = {
    "kuning": (255, 221, 0), "hijau": (57, 255, 20), "merah": (255, 59, 59),
    "biru": (0, 200, 255), "pink": (255, 80, 200), "putih": (255, 255, 255),
}


class CaptionRenderer:
    """Subtitle gaya TikTok: 2-3 kata per tampilan, kata yang sedang diucapkan disorot."""

    def __init__(self, words, style):
        self.style = style
        self.font_size = int(style.get("caption_size", 86))
        self.font = _load_font(self.font_size)
        self.hl = CAPTION_COLORS.get(style.get("caption_color", "kuning"), (255, 221, 0))
        self.upper = style.get("caption_upper", True)
        self.y_ratio = float(style.get("caption_pos", 0.68))
        self.max_words = int(style.get("caption_words", 3))
        self.groups = self._group(words)
        self.cache = {}

    def _group(self, words):
        groups, cur = [], []
        for w in words:
            txt = _clean_text(w["word"])
            if not txt.strip():
                continue
            if cur:
                gap = w["start"] - cur[-1]["e"]
                chars = sum(len(x["w"]) for x in cur) + len(txt)
                if (len(cur) >= self.max_words or gap > 0.6 or chars > 18
                        or cur[-1]["w"].endswith((".", "!", "?", ","))):
                    groups.append(cur)
                    cur = []
            cur.append({"s": w["start"], "e": w["end"], "w": txt})
        if cur:
            groups.append(cur)
        for i, g in enumerate(groups):  # tahan teks sampai kelompok berikutnya muncul
            nxt = groups[i + 1][0]["s"] if i + 1 < len(groups) else g[-1]["e"] + 0.4
            g_end = min(nxt, g[-1]["e"] + 0.6)
            for w in g:
                w["ge"] = g_end
        return groups

    def _render(self, gi, active):
        from PIL import Image, ImageDraw
        key = (gi, active)
        if key in self.cache:
            return self.cache[key]
        g = self.groups[gi]
        words = [(w["w"].upper() if self.upper else w["w"]).strip(",") for w in g]
        font = self.font
        stroke = max(4, self.font_size // 11)
        draw0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        space = draw0.textlength(" ", font=font)
        widths = [draw0.textlength(t, font=font) for t in words]
        # bungkus ke beberapa baris bila terlalu lebar
        max_w = OUT_W - 120
        lines, cur, cw = [], [], 0
        for i, wd in enumerate(widths):
            add = wd + (space if cur else 0)
            if cur and cw + add > max_w:
                lines.append(cur)
                cur, cw = [], 0
                add = wd
            cur.append(i)
            cw += add
        if cur:
            lines.append(cur)
        lh = int(self.font_size * 1.18)
        img = Image.new("RGBA", (OUT_W, lh * len(lines) + stroke * 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y = stroke * 2
        for line in lines:
            lw = sum(widths[i] for i in line) + space * (len(line) - 1)
            x = (OUT_W - lw) / 2
            for i in line:
                color = self.hl if i == active else (255, 255, 255)
                # bayangan
                d.text((x + 4, y + 6), words[i], font=font, fill=(0, 0, 0, 140),
                       stroke_width=stroke, stroke_fill=(0, 0, 0, 140))
                d.text((x, y), words[i], font=font, fill=color + (255,),
                       stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
                x += widths[i] + space
            y += lh
        arr = np.array(img)
        self.cache[key] = arr
        return arr

    def draw(self, frame, t):
        for gi, g in enumerate(self.groups):
            if g[0]["s"] <= t < g[0]["ge"]:
                active = -1
                for i, w in enumerate(g):
                    if w["s"] <= t:
                        active = i
                arr = self._render(gi, active)
                # efek "pop" kecil saat kelompok kata baru muncul
                age = t - g[0]["s"]
                if age < 0.08:
                    import cv2
                    sc = 0.88 + age / 0.08 * 0.12
                    nh, nw = int(arr.shape[0] * sc), int(arr.shape[1] * sc)
                    arr = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_LINEAR)
                y = int(OUT_H * self.y_ratio - arr.shape[0] / 2)
                _blend(frame, arr, (OUT_W - arr.shape[1]) // 2, y)
                return


def _title_image(title: str, style) -> np.ndarray:
    from PIL import Image, ImageDraw
    title = _clean_text(title).strip()
    size = int(style.get("title_size", 64))
    font = _load_font(size)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_w = OUT_W - 200
    words, lines, cur = title.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d0.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    lines = lines[:3]
    lh = int(size * 1.22)
    pad_x, pad_y = 40, 26
    tw = int(max(d0.textlength(l, font=font) for l in lines)) if lines else 0
    bw, bh = tw + pad_x * 2, lh * len(lines) + pad_y * 2
    img = Image.new("RGBA", (bw + 16, bh + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = style.get("title_bg", "putih")
    fill, txt = ((255, 255, 255, 250), (10, 10, 10)) if bg == "putih" else \
                ((255, 221, 0, 250), (10, 10, 10)) if bg == "kuning" else ((0, 0, 0, 215), (255, 255, 255))
    d.rounded_rectangle((8 + 6, 8 + 8, 8 + bw + 6, 8 + bh + 8), radius=28, fill=(0, 0, 0, 90))
    d.rounded_rectangle((8, 8, 8 + bw, 8 + bh), radius=28, fill=fill)
    y = 8 + pad_y
    for l in lines:
        lw = d.textlength(l, font=font)
        d.text((8 + (bw - lw) / 2, y), l, font=font, fill=txt)
        y += lh
    return np.array(img)


def _handle_image(text: str) -> np.ndarray:
    from PIL import Image, ImageDraw
    font = _load_font(40)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w = int(d0.textlength(text, font=font)) + 20
    img = Image.new("RGBA", (w, 70), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((10, 10), text, font=font, fill=(255, 255, 255, 170),
                             stroke_width=2, stroke_fill=(0, 0, 0, 120))
    return np.array(img)


def track_faces(src, start, dur, info: VideoInfo, sample_fps=3.0) -> list[tuple[float, float | None]]:
    """Kembalikan [(waktu, posisi_x_tengah_wajah 0..1 atau None)]."""
    import cv2
    det_w = 480
    det_h = int(round(info.height * det_w / info.width / 2)) * 2
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", src,
           "-t", f"{dur:.3f}", "-vf", f"fps={sample_fps},scale={det_w}:{det_h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_popen_kwargs())

    # Detektor utama: YuNet (model kecil, akurat, disertakan di folder models)
    detect = None
    model = os.path.join(APP_DIR, "models", "face_yunet.onnx")
    try:
        yn = cv2.FaceDetectorYN.create(model, "", (det_w, det_h), 0.6, 0.3, 20)

        def detect(img):
            _, faces = yn.detect(img)
            return [] if faces is None else [tuple(f[:4]) for f in faces]
    except Exception:
        # Cadangan: Haar cascade (ada di OpenCV 4.x)
        try:
            casc = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                                      "haarcascade_frontalface_default.xml"))
            if not casc.empty():
                def detect(img):
                    g = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
                    m = max(24, det_h // 12)
                    return list(casc.detectMultiScale(g, 1.15, 5, minSize=(m, m)))
        except Exception:
            pass
    res, i, n = [], 0, det_w * det_h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        x = None
        if detect:
            img = np.frombuffer(buf, np.uint8).reshape(det_h, det_w, 3)
            faces = detect(img)
            if len(faces):
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])  # wajah terbesar = pembicara
                x = float(fx + fw / 2) / det_w
        res.append((i / sample_fps, x))
        i += 1
    p.wait()
    return res


def _smooth_track(track, n_frames, fps):
    """Ubah titik deteksi jadi posisi kamera halus per frame (tanpa goyang)."""
    if not track or all(x is None for _, x in track):
        return None
    xs, last = [], None
    first = next(x for _, x in track if x is not None)
    for t, x in track:
        if x is None:
            x = last if last is not None else first
        xs.append(x)
        last = x
    xs = np.array(xs)
    # median untuk membuang deteksi salah
    k = 5
    pad = np.pad(xs, (k // 2, k // 2), mode="edge")
    med = np.array([np.median(pad[i:i + k]) for i in range(len(xs))])
    ts = np.array([t for t, _ in track])
    ft = np.arange(n_frames) / fps
    per = np.interp(ft, ts, med)
    # kamera "malas": hanya bergerak bila wajah keluar zona tengah, lalu meluncur halus
    out, cam = np.empty_like(per), per[0]
    target = cam
    for i, v in enumerate(per):
        if abs(v - target) > 0.06:
            target = v
        cam += (target - cam) * 0.08
        out[i] = cam
    return out


def render_clip(src: str, start: float, end: float, out_path: str, words: list[dict],
                style: dict, title: str = "", progress=None) -> str:
    import cv2

    info = probe(src)
    dur = max(0.5, end - start)
    fps = OUT_FPS
    n_frames = int(dur * fps)

    # ukuran decode (batasi 1080p supaya cepat)
    sw, sh = info.width, info.height
    if sh > 1080:
        sw, sh = int(round(sw * 1080 / sh / 2)) * 2, 1080

    layout = style.get("layout", "auto")
    is_vertical = sh >= sw
    cam = None
    if layout in ("auto", "face") and not is_vertical:
        track = track_faces(src, start, dur, info)
        found = sum(1 for _, x in track if x is not None)
        if found >= max(2, len(track) * 0.25):
            cam = _smooth_track(track, n_frames, fps)
        if cam is None and layout == "auto":
            layout = "blur"
        elif cam is None:
            layout = "center"
        else:
            layout = "face"
    if is_vertical:
        layout = "fill"

    # overlay statis
    cap = CaptionRenderer([{"start": w["start"] - start, "end": w["end"] - start, "word": w["word"]}
                           for w in words], style) if style.get("captions", True) and words else None
    title_img = _title_image(title, style) if style.get("title_on", True) and title.strip() else None
    title_secs = float(style.get("title_secs", 0) or 0)  # 0 = sepanjang video
    handle = style.get("handle", "").strip()
    handle_img = _handle_image(handle) if handle else None
    bar_on = style.get("progress_bar", True)
    bar_color = CAPTION_COLORS.get(style.get("caption_color", "kuning"), (255, 221, 0))[::-1]

    dec = subprocess.Popen(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", src,
         "-t", f"{dur:.3f}", "-vf", f"fps={fps},scale={sw}:{sh}", "-f", "rawvideo",
         "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_popen_kwargs())

    tmp_out = out_path + ".tmp.mp4"
    enc_cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(fps), "-i", "-"]
    if info.has_audio:
        enc_cmd += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src, "-map", "0:v", "-map", "1:a:0",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11" if style.get("loudnorm", True) else "anull",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    enc_cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-shortest", tmp_out]
    err_path = out_path + ".log"
    with open(err_path, "wb") as errf:
        enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=errf, **_popen_kwargs())
        frame_bytes = sw * sh * 3
        crop_w = int(sh * 9 / 16)
        fg_h = int(OUT_W * sh / sw)
        i = 0
        try:
            while i < n_frames:
                buf = dec.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                f = np.frombuffer(buf, np.uint8).reshape(sh, sw, 3)
                t = i / fps

                if layout == "face" or layout == "center":
                    cx = cam[min(i, len(cam) - 1)] if cam is not None else 0.5
                    x0 = int(np.clip(cx * sw - crop_w / 2, 0, sw - crop_w))
                    out = cv2.resize(f[:, x0:x0 + crop_w], (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
                elif layout == "fill":
                    scale = max(OUT_W / sw, OUT_H / sh)
                    rw, rh = int(sw * scale + 0.5), int(sh * scale + 0.5)
                    r = cv2.resize(f, (rw, rh), interpolation=cv2.INTER_LINEAR)
                    xo, yo = (rw - OUT_W) // 2, (rh - OUT_H) // 2
                    out = np.ascontiguousarray(r[yo:yo + OUT_H, xo:xo + OUT_W])
                else:  # blur: video utuh di tengah, latar belakang buram
                    small = cv2.resize(f, (OUT_W // 8, OUT_H // 8), interpolation=cv2.INTER_AREA)
                    small = cv2.GaussianBlur(small, (0, 0), 6)
                    out = cv2.resize(small, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
                    out = (out * 0.55).astype(np.uint8)
                    fg = cv2.resize(f, (OUT_W, fg_h), interpolation=cv2.INTER_AREA)
                    y0 = (OUT_H - fg_h) // 2
                    out[y0:y0 + fg_h] = fg

                if title_img is not None and (title_secs <= 0 or t < title_secs):
                    _blend(out, title_img, (OUT_W - title_img.shape[1]) // 2, int(OUT_H * 0.11))
                if handle_img is not None:
                    _blend(out, handle_img, (OUT_W - handle_img.shape[1]) // 2, int(OUT_H * 0.84))
                if cap:
                    cap.draw(out, t)
                if bar_on:
                    bw = int(OUT_W * (i + 1) / n_frames)
                    out[OUT_H - 14:OUT_H, :bw] = bar_color
                enc.stdin.write(out.tobytes())
                i += 1
                if progress and i % 15 == 0:
                    progress(i / n_frames)
        finally:
            try:
                enc.stdin.close()
            except Exception:
                pass
            dec.stdout.close()
            dec.wait()
            enc.wait()
    if enc.returncode != 0 or not os.path.exists(tmp_out):
        with open(err_path, "rb") as f:
            raise RuntimeError("Render gagal: " + f.read().decode("utf-8", "ignore")[-600:])
    os.replace(tmp_out, out_path)
    try:
        os.remove(err_path)
    except OSError:
        pass
    # thumbnail
    try:
        run_ffmpeg(["-ss", f"{min(1.0, dur / 2):.2f}", "-i", out_path, "-frames:v", "1",
                    "-vf", "scale=270:-2", out_path.rsplit(".", 1)[0] + ".jpg"])
    except Exception:
        pass
    return out_path


def write_srt(words, start, end, path, per_line=6):
    """Simpan juga subtitle .srt (berguna untuk diupload terpisah)."""
    ws = [w for w in words if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]

    def ts(x):
        x = max(0.0, x)
        h, r = divmod(x, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"

    with open(path, "w", encoding="utf-8") as f:
        for k in range(0, len(ws), per_line):
            chunk = ws[k:k + per_line]
            f.write(f"{k // per_line + 1}\n{ts(chunk[0]['start'] - start)} --> {ts(chunk[-1]['end'] - start)}\n")
            f.write(" ".join(w["word"] for w in chunk) + "\n\n")
