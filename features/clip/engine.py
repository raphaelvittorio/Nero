"""
Nero · Clip Maker - mesin pembuat clip pendek dari video panjang.

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
import threading
import wave
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30
RENDER_THREADS = max(1, min(4, (os.cpu_count() or 2) // 2))  # frame yang disusun bersamaan saat render

# --------------------------------------------------------------------------
# FFmpeg
# --------------------------------------------------------------------------
_FFMPEG = None
# folder utama aplikasi: tools/ (salinan ffmpeg), fonts/, dan models/ dipakai bersama semua fitur
APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


REF_MAX_SECONDS = 900  # clip referensi lebih dari 15 menit hampir pasti salah tempel (video penuh)


def download_reference(url: str, out_dir: str, cookies_browser: str | None = None,
                       max_seconds: int = REF_MAX_SECONDS, video: bool = False) -> dict:
    """Unduh clip referensi. Default audio saja (cukup untuk transkrip & pencocokan, jauh lebih cepat);
    video=True mengunduh gambarnya (maks 1280 px, tanpa digabung audio) untuk meniru gaya."""
    import yt_dlp
    from yt_dlp.utils import match_filter_func

    os.makedirs(out_dir, exist_ok=True)
    opts = {
        "outtmpl": os.path.join(out_dir, "ref.%(ext)s"),
        "format": "bv*[height<=1280]/bv*/b" if video else "ba/b",
        "ffmpeg_location": os.path.dirname(ffmpeg_exe()),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "match_filter": match_filter_func(f"duration <=? {max_seconds}"),
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True) or {}
    files = [f for f in os.listdir(out_dir) if f.startswith("ref.") and not f.endswith((".part", ".ytdl"))]
    if not files:
        dur = info.get("duration") or 0
        if dur > max_seconds:
            raise RuntimeError(f"terlalu panjang ({dur / 60:.0f} menit), bukan clip pendek")
        raise RuntimeError("tidak bisa diunduh")
    return {"path": os.path.join(out_dir, files[0]), "title": info.get("title") or url,
            "duration": info.get("duration") or 0}


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
CUDA_ERROR = ""  # alasan GPU tidak dipakai (ditampilkan di halaman)


def _register_cuda_dlls() -> None:
    """Pustaka CUDA dari paket pip nvidia-cublas-cu12 / nvidia-cudnn-cu12 tidak otomatis
    masuk PATH di Windows, jadi daftarkan foldernya sebelum ctranslate2 memuatnya."""
    if os.name != "nt":
        return
    try:
        import nvidia  # paket namespace milik nvidia-*-cu12
    except ImportError:
        return
    for base in list(getattr(nvidia, "__path__", [])):
        for sub in sorted(os.listdir(base)):
            b = os.path.join(base, sub, "bin")
            if os.path.isdir(b):
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(b)
                except OSError:
                    pass


_register_cuda_dlls()


def transcribe_device() -> str:
    """'cuda' bila kartu NVIDIA terdeteksi dan belum terbukti gagal, selain itu 'cpu'."""
    if _CUDA_BROKEN:
        return "cpu"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


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
    global _CUDA_BROKEN, CUDA_ERROR
    device = transcribe_device()

    # baca WAV sendiri (16 kHz mono) supaya tidak bergantung pada versi PyAV
    with wave.open(wav_path, "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    if device == "cuda":
        cb_errors = []

        def guarded(x):
            try:
                if progress:
                    progress(x)
            except BaseException as e:  # mis. dibatalkan pengguna: jangan dianggap GPU rusak
                cb_errors.append(e)
                raise

        try:
            return _transcribe_with(_whisper_model(model_size, "cuda"), audio, language, guarded)
        except Exception as e:
            if cb_errors:
                raise
            # Kartu NVIDIA ada, tapi pustaka CUDA (cuBLAS/cuDNN) tidak bisa dimuat -> pakai CPU
            _CUDA_BROKEN = True
            CUDA_ERROR = str(e)[:300]
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


# --------------------------------------------------------------------------
# Referensi dari pengguna: timeline hasil riset, titik waktu, link clip referensi, instruksi
# --------------------------------------------------------------------------
_TS = r"\d{1,3}(?::\d{1,2}){1,2}(?:\.\d+)?"      # 12:30, 1:02:30, 12:30.5
_TS_DOT = r"\d{1,3}\.\d{2}(?:\.\d{2})?"          # 12.30 (gaya penulisan jam di Indonesia), hanya untuk rentang
_SEP = r"\s*(?:-|–|—|~|→|->|to|sampai|hingga|s/d|sd)\s*"
_RANGE_RE = re.compile(rf"(?<![\d:.])(?:({_TS}){_SEP}({_TS})|({_TS_DOT}){_SEP}({_TS_DOT}))(?![\d:])", re.I)
_POINT_RE = re.compile(rf"^(?:[-*•>]|\d{{1,2}}[.)])?\s*(?:(?:clip|klip|momen|part|bagian)\s*\d*\s*[:.)\-]?\s*)?"
                       rf"[\[(]?({_TS})(?![\d:])[\])]?", re.I)
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_NEGATIVE = re.compile(r"\b(jangan|hindari|tanpa|kecuali|bukan|skip|lewati|avoid|except|don'?t|no)\b", re.I)
BRIEF_STOP = set("""
cari carikan buat buatkan bikin bikinin momen moment momennya clip klip clipnya video bagian tentang soal
fokus utamakan gaya judul hook caption durasi detik menit tolong mohon pilih pilihkan ambil ambilkan tampilkan
terutama khususnya kira sekitar contoh misalnya sesuai referensi timeline yang find make focus about style
""".split())


def parse_ts(v: str) -> float:
    """'12:30' -> 750, '1:02:30' -> 3750, '12.30' -> 750 (penulisan jam gaya Indonesia)."""
    v = v.strip()
    parts = v.split(":") if ":" in v else v.split(".")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def _clean_note(t: str) -> str:
    return re.sub(r"^[\s\-–—:|•*>.,)\]]+|[\s\-–—:|•*>,(\[]+$", "", t).strip()


def parse_brief(text: str) -> dict:
    """Pisahkan isi kolom referensi menjadi:
    ranges (timeline mulai-selesai), points (satu titik waktu), links (clip referensi), instructions (teks bebas)."""
    ranges, points, links, rest = [], [], [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        urls = _URL_RE.findall(line)
        if urls:
            links += [u.rstrip(".,;)]") for u in urls]
            continue
        m = _RANGE_RE.search(line)
        if m:
            a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            note = _clean_note(line[m.end():]) or _clean_note(line[:m.start()])
            ranges.append({"start": parse_ts(a), "end": parse_ts(b), "note": note[:200]})
            continue
        m = _POINT_RE.match(line)
        if m:
            points.append({"t": parse_ts(m.group(1)), "note": _clean_note(line[m.end():])[:200]})
            continue
        rest.append(line)
    return {"ranges": ranges, "points": points, "links": list(dict.fromkeys(links)),
            "instructions": "\n".join(rest)[:4000]}


def brief_keywords(text: str, n: int = 12) -> tuple[list[str], list[str]]:
    """Kata kunci dari instruksi bebas: (dicari, dihindari). "Frasa dalam kutip" dicocokkan utuh.
    Klausa yang mengandung 'jangan/hindari/tanpa...' masuk daftar yang dihindari."""
    want, avoid = [], []
    for clause in re.split(r"[\n.;,]+", text or ""):
        bucket = avoid if _NEGATIVE.search(clause) else want
        bucket += [q.lower().strip() for q in re.findall(r"[\"“”']([^\"“”']{3,80})[\"“”']", clause)]
        rest = re.sub(r"[\"“”'][^\"“”']*[\"“”']", " ", clause)
        bucket += [w for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", rest.lower())
                   if w not in STOPWORDS and w not in FILLER and w not in BRIEF_STOP and not _NEGATIVE.fullmatch(w)]
    return list(dict.fromkeys(want))[:n], list(dict.fromkeys(avoid))[:n]


def snap_range(segments, start: float, end: float, tol: float = 2.0) -> tuple[float, float]:
    """Rapikan ke awal/akhir kalimat terdekat bila jaraknya dekat (timeline riset biasanya dibulatkan)."""
    if segments:
        s = min(segments, key=lambda x: abs(x["start"] - start))
        if abs(s["start"] - start) <= tol:
            start = s["start"]
        e = min(segments, key=lambda x: abs(x["end"] - end))
        if abs(e["end"] - end) <= tol and e["end"] > start:
            end = e["end"]
    return round(start, 2), round(end, 2)


def _text_between(segments, start, end) -> str:
    return " ".join(s["text"] for s in segments if s["end"] > start + 0.1 and s["start"] < end - 0.1)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[0-9a-zà-ÿ]+", text.lower())


def match_reference(segments, ref_segments, min_ratio: float = 0.35, n: int = 3) -> dict | None:
    """Cari bagian video panjang yang ucapannya sama dengan clip referensi (mis. clip orang lain
    dari podcast yang sama). Dicocokkan per 3 kata berurutan, jadi tahan terhadap salah dengar transkrip.
    Hasil: {start, end, ratio} atau None bila tidak ketemu."""
    words = [w for s in segments for w in s.get("words", [])]
    toks = [(t, wi) for wi, w in enumerate(words) for t in _tokens(w["word"])]
    ref = [t for s in ref_segments for t in _tokens(s["text"])]
    if len(ref) < n + 3 or len(toks) < n:
        return None
    index: dict[tuple, list[int]] = {}
    for k in range(len(toks) - n + 1):
        index.setdefault(tuple(t for t, _ in toks[k:k + n]), []).append(k)
    hits = sorted((k, j) for j in range(len(ref) - n + 1) for k in index.get(tuple(ref[j:j + n]), ()))
    if not hits:
        return None
    # jendela terpadat: paling banyak potongan referensi berbeda yang cocok dalam rentang sepanjang clip
    span = int(len(ref) * 1.6) + 10
    cnt: dict[int, int] = {}
    lo, best = 0, (0, 0, 0)
    for hi, (k, j) in enumerate(hits):
        cnt[j] = cnt.get(j, 0) + 1
        while k - hits[lo][0] > span:
            jj = hits[lo][1]
            cnt[jj] -= 1
            if not cnt[jj]:
                del cnt[jj]
            lo += 1
        if len(cnt) > best[0]:
            best = (len(cnt), lo, hi)
    found, lo, hi = best
    ratio = found / (len(ref) - n + 1)
    if ratio < min_ratio:
        return None
    # buang kecocokan nyasar (frasa umum di tempat lain) yang tidak segaris dengan mayoritas
    win = hits[lo:hi + 1]
    mid = float(np.median([k - j for k, j in win]))
    win = [(k, j) for k, j in win if abs(k - j - mid) <= 0.15 * len(ref) + 5]
    k0, k1 = min(k for k, _ in win), max(k for k, _ in win) + n - 1
    j0, j1 = min(j for _, j in win), max(j for _, j in win) + n - 1
    # kata awal/akhir referensi yang tidak cocok tetap dihitung, supaya clip tidak terpotong
    k0, k1 = max(0, k0 - j0), min(len(toks) - 1, k1 + (len(ref) - 1 - j1))
    return {"start": words[toks[k0][1]]["start"], "end": words[toks[k1][1]]["end"], "ratio": round(ratio, 2)}


def _local_meta(segments, start, end, note="") -> dict:
    """Judul, caption & hashtag tanpa AI untuk rentang waktu tertentu."""
    text = _text_between(segments, start, end)
    first = next((s["text"] for s in segments if s["end"] > start + 0.1), text)
    title = note[:90] if note else _make_title(first if len(first.split()) >= 4 else text or "Clip")
    return {"title": title, "caption": _make_title(text, 16) if text else title,
            "hashtags": _hashtags(text), "text": text}


def _overlaps(a0, a1, b0, b1, slack=1.0) -> bool:
    return not (a1 <= b0 + slack or a0 >= b1 - slack)


def find_highlights_heuristic(segments, energy, n_clips=5, min_len=20, max_len=60, keywords=(), avoid=(),
                              points=(), fixed=(), taken=()) -> list[dict]:
    """Pilih momen tanpa AI.
    fixed  : rentang wajib dari pengguna [{start, end, note, ref}] -> selalu ikut dalam hasil
    points : titik waktu wajib [{t, note}] -> dipilih momen terbaik yang mencakup titik itu
    taken  : rentang yang sudah dipakai (tidak ikut hasil, hanya dihindari)
    n_clips: jumlah momen otomatis tambahan; keywords/avoid menaikkan/menurunkan skor."""
    hop = 0.5
    e_mean, e_std = float(np.mean(energy)), float(np.std(energy) + 1e-6)
    keywords, avoid = [k.lower() for k in keywords], [k.lower() for k in avoid]

    def score_of(i, j):
        start, end = segments[i]["start"], segments[j]["end"]
        dur = max(0.5, end - start)
        text = " ".join(s["text"] for s in segments[i:j + 1])
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
        clean = 1.5 if segments[j]["text"].rstrip().endswith((".", "!", "?")) else -1.0
        length_pref = -abs(dur - (min_len + max_len) / 2) / max_len
        low = text.lower()
        topic = sum(3.0 for k in keywords if k in low) + (1.5 if any(k in first for k in keywords) else 0)
        topic -= sum(4.0 for k in avoid if k in low)

        score = hook + kw + rate_score + filler + loud + peaks + silent + excl + clean + length_pref + topic
        return {"start": start, "end": end, "score": score, "text": text,
                "first": segments[i]["text"], "topic": topic > 0}

    cands = []
    for i in range(len(segments)):
        for j in range(i, len(segments)):
            dur = segments[j]["end"] - segments[i]["start"]
            if dur > max_len:
                break
            if dur >= min_len:
                cands.append(score_of(i, j))
    if not cands and segments:  # video lebih pendek dari durasi minimum
        cands = [score_of(0, len(segments) - 1)]

    blocked = [tuple(x) for x in taken] + [(f["start"], f["end"]) for f in fixed]
    free = lambda a, b: all(not _overlaps(a, b, x, y) for x, y in blocked)  # noqa: E731
    chosen = []

    for f in fixed:  # timeline pengguna: skornya tetap dihitung supaya bisa dibandingkan
        idx = [k for k, s in enumerate(segments) if s["end"] > f["start"] + 0.1 and s["start"] < f["end"] - 0.1]
        c = score_of(idx[0], idx[-1]) if idx else {"score": 0.0, "text": "", "first": "", "topic": False}
        chosen.append({**c, "start": f["start"], "end": f["end"], "ref": f.get("ref", "timeline"),
                       "note": f.get("note", ""), "ratio": f.get("ratio")})

    for pt in points:  # titik waktu: momen terbaik yang dimulai sedikit sebelum titik itu
        t = pt["t"]
        opts = [c for c in cands if t - min(15, max_len * 0.3) <= c["start"] <= t + 1 and c["end"] >= t + 4
                and free(c["start"], c["end"])]
        if opts:
            c = max(opts, key=lambda x: x["score"])
        elif segments:
            i = max([k for k, s in enumerate(segments) if s["start"] <= t + 1] or [0])
            j = i
            while j + 1 < len(segments) and segments[j]["end"] - segments[i]["start"] < (min_len + max_len) / 2:
                j += 1
            c = score_of(i, j)
        else:
            continue
        chosen.append({**c, "ref": "titik", "t": t, "note": pt.get("note", "")})
        blocked.append((c["start"], c["end"]))

    n_auto = 0
    for c in sorted(cands, key=lambda x: -x["score"]):
        if n_auto >= n_clips:
            break
        if free(c["start"], c["end"]):
            chosen.append(c)
            blocked.append((c["start"], c["end"]))
            n_auto += 1
    if not chosen:
        return []

    scores = [c["score"] for c in chosen]
    lo, hi = min(scores), max(scores)
    out = []
    for c in chosen:
        norm = 0.5 if hi == lo else (c["score"] - lo) / (hi - lo)
        viral = int(round(55 + norm * 40))
        ref, note = c.get("ref"), c.get("note") or ""
        if ref == "timeline":
            reasons = ["dari timeline riset Anda"]
        elif ref == "link":
            reasons = [f"sama dengan clip referensi ({c.get('ratio') or 0:.0%} kata cocok)"]
        elif ref == "titik":
            reasons = [f"mencakup titik {_fmt(c['t'])} dari riset Anda" + (f" ({note})" if note else "")]
            note = ""  # catatan titik bukan judul
        else:
            reasons = []
            if c.get("topic"):
                reasons.append("sesuai instruksi/topik Anda")
            if "?" in c["first"]:
                reasons.append("dibuka dengan pertanyaan")
            if any(k in c["first"].lower() for k in HOOK_WORDS):
                reasons.append("kalimat pembuka kuat")
            if "!" in c["text"]:
                reasons.append("emosi/penekanan tinggi")
            if not reasons:
                reasons.append("bicara padat dan jelas")
        out.append({"start": round(c["start"], 2), "end": round(c["end"], 2), "score": viral,
                    "reason": ", ".join(reasons), "ref": ref, **_local_meta(segments, c["start"], c["end"], note)})
    out.sort(key=lambda c: c["start"])
    return out


# Struktur jawaban yang dijamin API (structured outputs), jadi tidak perlu menebak JSON dari teks.
CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number", "description": "detik mulai"},
                    "end": {"type": "number", "description": "detik selesai"},
                    "title": {"type": "string", "description": "judul hook singkat, maks 8 kata"},
                    "score": {"type": "integer", "description": "potensi viral 0-100"},
                    "reason": {"type": "string", "description": "alasan singkat"},
                    "caption": {"type": "string", "description": "caption postingan 1-2 kalimat"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "ref": {"type": "integer", "description": "nomor TIMELINE WAJIB yang diisi datanya, 0 untuk clip baru"},
                },
                "required": ["start", "end", "title", "score", "reason", "caption", "hashtags", "ref"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["clips"],
    "additionalProperties": False,
}
# Model yang mendukung fallback otomatis di server bila permintaan ditolak pengaman.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
AI_TRANSCRIPT_LIMIT = 800_000  # karakter (~200 ribu token): cukup untuk video beberapa jam


def _brief_prompt(brief: dict) -> str:
    """Bagian prompt dari kolom 'Referensi & instruksi' milik pengguna."""
    parts = []
    instr = (brief.get("instructions") or "").strip()
    if instr:
        parts.append("INSTRUKSI DARI PENGGUNA (utamakan saat memilih momen dan menulis judul/caption):\n"
                     f"<instruksi>\n{instr}\n</instruksi>")
    examples = brief.get("examples") or []
    if examples:
        parts.append("CONTOH CLIP REFERENSI yang disukai pengguna (dari video lain). Cari momen yang jenis, "
                     "energi, dan gaya hook-nya mirip; isinya tidak harus sama:\n"
                     + "\n".join(f'Contoh {k}: "{e}"' for k, e in enumerate(examples, 1)))
    fixed = brief.get("fixed") or []
    if fixed:
        parts.append("TIMELINE WAJIB hasil riset pengguna. Semuanya PASTI dijadikan clip dengan waktu ini. "
                     "Untuk masing-masing, kembalikan satu item berisi title, caption, hashtags, score, reason "
                     "dengan ref = nomornya (start/end salin dari sini):\n"
                     + "\n".join(f"#{k} [{f['start']:.1f}-{f['end']:.1f}]"
                                 + (f" catatan pengguna: {f['note']}" if f.get("note") else "")
                                 for k, f in enumerate(fixed, 1)))
    points = brief.get("points") or []
    if points:
        parts.append("TITIK WAKTU WAJIB hasil riset pengguna. Setiap titik berikut harus masuk ke salah satu "
                     "clip BARU (ref = 0) yang dimulai sedikit sebelum titik itu:\n"
                     + "\n".join(f"- detik {pt['t']:.1f}" + (f" ({pt['note']})" if pt.get("note") else "")
                                 for pt in points))
    return "\n\n".join(parts)


def find_highlights_ai(segments, api_key, n_clips=5, min_len=20, max_len=60,
                       model="claude-sonnet-5-5", video_title="", brief=None) -> tuple[list[dict], str]:
    """Memakai Claude API untuk memilih momen paling 'viral'.
    n_clips = jumlah clip BARU. brief (opsional): {instructions, examples, fixed, points} dari pengguna;
    clip 'fixed' selalu dikembalikan dengan waktu persis seperti yang diberikan.
    Hasil: (daftar clip, catatan untuk pengguna atau "")."""
    import anthropic

    brief = brief or {}
    fixed, points = brief.get("fixed") or [], brief.get("points") or []
    lines, total, cut_at = [], 0, None
    for s in segments:
        line = f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
        total += len(line) + 1
        if total > AI_TRANSCRIPT_LIMIT:
            cut_at = s["start"]
            break
        lines.append(line)
    note = (f"Transkrip sangat panjang: AI hanya membaca sampai menit {cut_at / 60:.0f}." if cut_at else "")
    extra = _brief_prompt(brief)
    if n_clips > 0:
        task = (f"Pilih {n_clips} potongan BARU terbaik (ref = 0) untuk dijadikan video pendek"
                + (", tidak tumpang tindih dengan TIMELINE WAJIB" if fixed else "") + ".")
    else:
        task = "Tidak perlu memilih potongan baru; cukup isi data untuk setiap TIMELINE WAJIB."
    prompt = f"""Kamu adalah editor video pendek (TikTok/Reels/Shorts) yang sangat paham konten viral.
Berikut transkrip video "{video_title}" dengan waktu dalam detik.

{chr(10).join(lines)}
{(chr(10) + extra + chr(10)) if extra else ""}
{task} Aturan:
- Durasi tiap potongan baru {min_len}-{max_len} detik, tidak saling tumpang tindih.
- Mulai tepat di awal kalimat yang langsung menarik perhatian (hook kuat di 3 detik pertama).
- Akhiri di akhir kalimat/gagasan yang tuntas.
- Potongan harus bisa dipahami tanpa menonton video aslinya.
- title: judul hook singkat (maks 8 kata) yang tampil di atas video.
- caption: caption postingan 1-2 kalimat; hashtags: 3-8 hashtag relevan.
- Ikuti instruksi pengguna di atas bila ada, kecuali yang bertentangan dengan format jawaban.
Gunakan bahasa yang sama dengan bahasa transkrip, kecuali pengguna meminta bahasa lain."""

    client = anthropic.Anthropic(api_key=api_key, max_retries=3)
    params = {
        "model": model,
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": CLIP_SCHEMA}},
    }
    try:
        if model in FALLBACK_MODELS:
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                               fallbacks="default", **params)
        else:
            resp = client.messages.create(**params)
    except anthropic.AuthenticationError as e:
        raise RuntimeError("Claude API key tidak valid.") from e
    except anthropic.PermissionDeniedError as e:
        raise RuntimeError("API key tidak punya akses ke model ini.") from e
    except anthropic.NotFoundError as e:
        raise RuntimeError(f"Model AI '{model}' tidak ditemukan. Periksa nama model di Pengaturan.") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Batas pemakaian Claude API tercapai, coba lagi nanti.") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API error {e.status_code}: {e.message}"[:300]) from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError("Tidak bisa terhubung ke Claude API. Periksa koneksi internet.") from e

    if resp.stop_reason == "refusal":
        raise RuntimeError("AI menolak memproses transkrip ini.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Jawaban AI terpotong.")
    texts = [b.text for b in resp.content if b.type == "text"]
    if not texts:
        raise RuntimeError("Jawaban AI kosong.")
    clips = json.loads(texts[-1])["clips"]  # blok teks terakhir = jawaban model yang selesai

    starts = [s["start"] for s in segments]
    ends = [s["end"] for s in segments]
    fixed_out: dict[int, dict] = {}
    new = []
    for c in clips:
        try:
            score = max(0, min(100, int(round(float(c.get("score", 70))))))
        except (TypeError, ValueError):
            score = 70
        meta = {
            "title": str(c.get("title", ""))[:90],
            "score": score,
            "reason": str(c.get("reason", "")),
            "caption": str(c.get("caption", "")),
            "hashtags": [h if h.startswith("#") else "#" + h
                         for h in (str(x).strip().replace(" ", "") for x in c.get("hashtags", [])) if h][:8],
        }
        try:
            ref = int(c.get("ref") or 0)
        except (TypeError, ValueError):
            ref = 0
        if 1 <= ref <= len(fixed) and ref not in fixed_out:
            f = fixed[ref - 1]  # waktu dari pengguna yang dipakai, bukan tebakan AI
            fixed_out[ref] = {"start": f["start"], "end": f["end"], **meta, "ref": f.get("ref", "timeline"),
                              "text": _text_between(segments, f["start"], f["end"])}
            continue
        st, en = float(c["start"]), float(c["end"])
        st = min(starts, key=lambda x: abs(x - st))  # rapikan ke batas kalimat
        en = min(ends, key=lambda x: abs(x - en))
        if en - st < 5 or any(_overlaps(st, en, f["start"], f["end"], 2.0) for f in fixed):
            continue
        covers = any(st - 1 <= pt["t"] <= en for pt in points)
        new.append({"start": round(st, 2), "end": round(en, 2), **meta, "ref": "titik" if covers else None,
                    "text": " ".join(s["text"] for s in segments if s["start"] >= st - 0.1 and s["end"] <= en + 0.1)})
    for k, f in enumerate(fixed, 1):  # AI lupa mengisi salah satu timeline: tetap dibuat
        if k not in fixed_out:
            fixed_out[k] = {"start": f["start"], "end": f["end"], "score": 0, "ref": f.get("ref", "timeline"),
                            "reason": "dari timeline riset Anda",
                            **_local_meta(segments, f["start"], f["end"], f.get("note", ""))}
    new.sort(key=lambda c: (c["ref"] != "titik", -c["score"]))
    out = list(fixed_out.values()) + new[:max(n_clips, len(points))]
    out.sort(key=lambda c: c["start"])
    return out, note


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


FONTS_DIR = os.path.join(APP_DIR, "fonts")
# nama -> (berkas di fonts/ atau di folder font Windows, nilai sumbu font variabel / nama variasinya)
CAPTION_FONTS = {
    "impact": ("impact.ttf", None),
    "montserrat": ("Montserrat[wght].ttf", [800]),
    "anton": ("Anton-Regular.ttf", None),
    "bebas": ("BebasNeue-Regular.ttf", None),
    "poppins": ("Poppins-ExtraBold.ttf", None),
    "arial": ("ariblk.ttf", None),            # Arial Black bawaan Windows
    "segoe": ("seguibl.ttf", None),           # Segoe UI Black (Windows): bulat modern
    "bahnschrift": ("bahnschrift.ttf", b"Bold Condensed"),  # Windows: ramping teknis
    "verdana": ("verdanab.ttf", None),        # Windows: lebar, sangat mudah dibaca
    "georgia": ("georgiab.ttf", None),        # Windows: berkait (serif), kesan elegan/berita
    "comic": ("comicbd.ttf", None),           # Comic Sans Bold (Windows): santai, lucu
}


def _style_font(style: dict, size: int):
    """Font subtitle/judul sesuai pilihan gaya; bila berkasnya tidak ada, pakai font tebal bawaan."""
    return _font_by_key(style.get("caption_font", "impact"), size)


def _font_by_key(key: str, size: int):
    file, var = CAPTION_FONTS.get(key, CAPTION_FONTS["impact"])
    dirs = [FONTS_DIR] + ([os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")] if os.name == "nt" else [])
    for d in dirs:
        path = os.path.join(d, file)
        if os.path.isfile(path):
            font = _load_font(size, path)
            if var:
                try:
                    if isinstance(var, bytes):
                        font.set_variation_by_name(var)
                    else:
                        font.set_variation_by_axes(var)
                except Exception:
                    pass
            return font
    return _load_font(size)


_KEY_WORDS = set(HOOK_WORDS)


def _is_key_word(word: str) -> bool:
    """Kata yang disorot saat 'Sorot kata kunci' aktif: angka, kata pemancing perhatian, seruan."""
    w = word.lower().strip(".,!?\"'()")
    return bool(re.search(r"\d", w)) or w in _KEY_WORDS or word.rstrip().endswith("!")


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
    "oranye": (255, 140, 0), "ungu": (170, 90, 255), "toska": (0, 230, 190),
}
_STROKE = {1: (2, 22), 2: (4, 11), 3: (6, 7)}  # tingkat garis tepi -> (minimal px, ukuran font / angka ini)


def _stroke_px(size: int, level) -> int:
    """Tebal garis tepi huruf: 0 tanpa, 1 tipis, 2 sedang (bawaan), 3 tebal."""
    level = int(level or 0)
    if level <= 0:
        return 0
    lo, div = _STROKE[min(3, level)]
    return max(lo, size // div)


def _light(rgb) -> bool:
    """Warna terang (mis. kuning, putih): tulisan di atasnya sebaiknya gelap."""
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] > 185


def _resize_rgba(arr: np.ndarray, scale: float) -> np.ndarray:
    import cv2
    nh, nw = max(1, int(arr.shape[0] * scale)), max(1, int(arr.shape[1] * scale))
    return cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_LINEAR)


class CaptionRenderer:
    """Subtitle gaya TikTok: 1-4 kata per tampilan. Kata yang sedang diucapkan disorot dengan warna,
    kotak berwarna, atau gaya karaoke (kata yang sudah diucapkan tetap berwarna)."""

    def __init__(self, words, style):
        self.style = style
        self.font_size = int(style.get("caption_size", 86))
        self.font = _style_font(style, self.font_size)
        self.emphasis = bool(style.get("caption_emphasis", False))
        self.font_big = _style_font(style, int(self.font_size * 1.15)) if self.emphasis else self.font
        self.hl = CAPTION_COLORS.get(style.get("caption_color", "kuning"), (255, 221, 0))
        self.base = CAPTION_COLORS.get(style.get("caption_base", "putih"), (255, 255, 255))
        self.upper = style.get("caption_upper", True)
        self.y_ratio = float(style.get("caption_pos", 0.68))
        self.max_words = int(style.get("caption_words", 3))
        self.mode = style.get("caption_highlight", "warna")   # warna | kotak | karaoke | tanpa
        self.anim = style.get("caption_anim", "pop")          # pop | bounce | naik | tanpa
        self.stroke = _stroke_px(self.font_size, style.get("caption_stroke", 2))
        self.shadow = bool(style.get("caption_shadow", True))
        self.box = bool(style.get("caption_box", False))      # kotak gelap transparan di belakang subtitle
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
            cur.append({"s": w["start"], "e": w["end"], "w": txt, "x": self.emphasis and _is_key_word(txt)})
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
        fonts = [self.font_big if w.get("x") else self.font for w in g]   # kata kunci sedikit lebih besar
        stroke, size, mode = self.stroke, self.font_size, self.mode
        draw0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        space = draw0.textlength(" ", font=self.font)
        widths = [draw0.textlength(t, font=f) for t, f in zip(words, fonts)]
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
        line_h = [int(max(fonts[i].size for i in line) * 1.18) for line in lines]
        line_w = [sum(widths[i] for i in line) + space * (len(line) - 1) for line in lines]
        # kotak sorot kata: tulisan putih bergaris tepi tipis di kotak gelap, tulisan gelap tanpa garis tepi di
        # kotak terang. Tepi kotak memperhitungkan garis tepi supaya kotaknya tetap terlihat jelas
        box_sw = 0 if _light(self.hl) else max(2, size // 22)
        kx, ky = int(size * 0.18) + box_sw, int(size * 0.12) + box_sw
        bx, by = int(size * 0.32), int(size * 0.14)           # tepi kotak gelap di belakang subtitle
        m = max(stroke * 2, kx + 4 if mode == "kotak" else 0, by + 4 if self.box else 0) + 8
        img = Image.new("RGBA", (OUT_W, sum(line_h) + 2 * m), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if self.box:
            w0 = max(line_w)
            d.rounded_rectangle(((OUT_W - w0) / 2 - bx, m - by, (OUT_W + w0) / 2 + bx, m + sum(line_h) + by // 2),
                                radius=int(size * 0.28), fill=(0, 0, 0, 165))
        y = m
        for line, lh, lw in zip(lines, line_h, line_w):
            x = (OUT_W - lw) / 2
            top = max(fonts[i].getmetrics()[0] for i in line)
            for i in line:
                f = fonts[i]
                dy = top - f.getmetrics()[0]  # garis dasar kata besar & kecil disamakan
                spoken = i <= active if mode == "karaoke" else (i == active and mode == "warna")
                color = self.hl if (spoken or g[i].get("x")) else self.base
                sw = stroke
                if mode == "kotak" and i == active:
                    _, cap_top, _, base = d.textbbox((x, y + dy), "H", font=f)
                    low = 0 if self.upper else int(f.size * 0.12)   # ruang untuk huruf g, p, y
                    d.rounded_rectangle((x - kx, cap_top - ky, x + widths[i] + kx, base + ky + low),
                                        radius=int(size * 0.2), fill=self.hl + (255,))
                    color, sw = ((15, 15, 15), 0) if _light(self.hl) else ((255, 255, 255), box_sw)
                if self.shadow and not (mode == "kotak" and i == active):
                    d.text((x + max(3, size // 22), y + dy + max(4, size // 15)), words[i], font=f,
                           fill=(0, 0, 0, 140), stroke_width=sw, stroke_fill=(0, 0, 0, 140))
                d.text((x, y + dy), words[i], font=f, fill=color + (255,),
                       stroke_width=sw, stroke_fill=(0, 0, 0, 255))
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
                # animasi saat kelompok kata baru muncul
                age, dy = t - g[0]["s"], 0
                if self.anim == "pop" and age < 0.08:
                    arr = _resize_rgba(arr, 0.88 + age / 0.08 * 0.12)
                elif self.anim == "bounce" and age < 0.2:      # membesar melewati ukuran asli lalu kembali
                    k = age / 0.2
                    arr = _resize_rgba(arr, 0.6 + 0.52 * k / 0.55 if k < 0.55 else 1.12 - 0.12 * (k - 0.55) / 0.45)
                elif self.anim == "naik" and age < 0.15:       # naik dari bawah sambil muncul perlahan
                    k = age / 0.15
                    dy = int((1 - k) * 0.45 * self.font_size)
                    arr = arr.copy()
                    arr[..., 3] = (arr[..., 3] * k).astype(np.uint8)
                y = int(OUT_H * self.y_ratio - arr.shape[0] / 2) + dy
                _blend(frame, arr, (OUT_W - arr.shape[1]) // 2, y)
                return


def _title_image(title: str, style) -> np.ndarray:
    from PIL import Image, ImageDraw
    title = _clean_text(title).strip()
    size = int(style.get("title_size", 64))
    font = _style_font(style, size)
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
    bg = style.get("title_bg", "putih")
    if bg == "tanpa":  # tulisan putih bergaris tepi hitam tanpa kotak
        stroke = max(3, size // 10)
        tw = int(max(d0.textlength(l, font=font) for l in lines)) if lines else 0
        img = Image.new("RGBA", (tw + stroke * 4 + 16, lh * len(lines) + stroke * 4 + 16), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y = stroke * 2 + 4
        for l in lines:
            x = (img.width - d.textlength(l, font=font)) / 2
            d.text((x + 4, y + 6), l, font=font, fill=(0, 0, 0, 130), stroke_width=stroke, stroke_fill=(0, 0, 0, 130))
            d.text((x, y), l, font=font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            y += lh
        return np.array(img)
    pad_x, pad_y = 40, 26
    tw = int(max(d0.textlength(l, font=font) for l in lines)) if lines else 0
    bw, bh = tw + pad_x * 2, lh * len(lines) + pad_y * 2
    img = Image.new("RGBA", (bw + 16, bh + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill, txt = TITLE_BOXES.get(bg, TITLE_BOXES["putih"])
    d.rounded_rectangle((8 + 6, 8 + 8, 8 + bw + 6, 8 + bh + 8), radius=28, fill=(0, 0, 0, 90))
    d.rounded_rectangle((8, 8, 8 + bw, 8 + bh), radius=28, fill=fill)
    y = 8 + pad_y
    for l in lines:
        lw = d.textlength(l, font=font)
        d.text((8 + (bw - lw) / 2, y), l, font=font, fill=txt)
        y += lh
    return np.array(img)


# gaya judul -> (warna kotak RGBA, warna tulisan)
TITLE_BOXES = {
    "putih": ((255, 255, 255, 250), (10, 10, 10)),
    "kuning": ((255, 221, 0, 250), (10, 10, 10)),
    "hitam": ((0, 0, 0, 215), (255, 255, 255)),
    "merah": ((232, 40, 40, 248), (255, 255, 255)),
}


def _handle_image(text: str) -> np.ndarray:
    from PIL import Image, ImageDraw
    font = _load_font(40)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w = int(d0.textlength(text, font=font)) + 20
    img = Image.new("RGBA", (w, 70), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((10, 10), text, font=font, fill=(255, 255, 255, 170),
                             stroke_width=2, stroke_fill=(0, 0, 0, 120))
    return np.array(img)


def track_faces(src, start, dur, info: VideoInfo, sample_fps=3.0) -> list[tuple[float, list]]:
    """Kembalikan [(waktu, [(cx, cy, w, h), ...])]: semua wajah (0..1), terbesar lebih dulu."""
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
        faces = []
        if detect:
            img = np.frombuffer(buf, np.uint8).reshape(det_h, det_w, 3)
            faces = sorted(((float(fx + fw / 2) / det_w, float(fy + fh / 2) / det_h,
                             float(fw) / det_w, float(fh) / det_h) for fx, fy, fw, fh in detect(img)),
                           key=lambda f: -f[2] * f[3])
        res.append((i / sample_fps, faces))
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


def _two_people(track) -> bool:
    """Dua wajah berdampingan (podcast/wawancara) di sebagian besar potongan?"""
    if not track:
        return False
    hits = 0
    for _, faces in track:
        if len(faces) >= 2:
            a, b = faces[0], faces[1]
            if b[2] * b[3] >= 0.35 * a[2] * a[3] and abs(a[0] - b[0]) > 0.15:
                hits += 1
    return hits >= max(2, 0.5 * len(track))


def _split_tracks(track, n_frames, fps):
    """Jalur kamera orang kiri & kanan: [(xs, ys), (xs, ys)] per frame, atau None."""
    sides, last = [[], []], [None, None]
    for t, faces in track:
        pts = [None, None]
        if len(faces) >= 2:
            a, b = sorted(faces[:2], key=lambda f: f[0])
            pts = [(a[0], a[1]), (b[0], b[1])]
        elif len(faces) == 1 and last[0] and last[1]:
            f = faces[0]  # satu wajah saja: tempelkan ke sisi yang posisinya terdekat
            k = 0 if abs(f[0] - last[0][0]) <= abs(f[0] - last[1][0]) else 1
            pts[k] = (f[0], f[1])
        for k in (0, 1):
            if pts[k]:
                last[k] = pts[k]
            sides[k].append((t, pts[k]))
    out = []
    for side in sides:
        xs = _smooth_track([(t, p[0] if p else None) for t, p in side], n_frames, fps)
        ys = _smooth_track([(t, p[1] if p else None) for t, p in side], n_frames, fps)
        if xs is None or ys is None:
            return None
        out.append((xs, ys))
    return out


def _decode_size(info: VideoInfo) -> tuple[int, int]:
    """Ukuran decode: sisi pendek maks 1080 px supaya cepat.
    (Dulu tinggi dibatasi 1080, sehingga video vertikal 1080x1920 ikut dikecilkan lalu diperbesar lagi.)"""
    sw, sh = info.width, info.height
    short = min(sw, sh)
    if short > 1080:
        k = 1080 / short
        sw, sh = int(round(sw * k / 2)) * 2, int(round(sh * k / 2)) * 2
    return sw, sh


def _plan_layout(src, start, dur, info, style, sw, sh, n_frames, fps):
    """Tentukan tata letak & jalur kamera. Hasil: (layout, cam, split)."""
    if sh >= sw:
        return "fill", None, None  # video sudah vertikal
    layout = style.get("layout", "auto")
    if layout not in ("auto", "face", "split"):
        return layout, None, None  # blur / center
    track = track_faces(src, start, dur, info)
    if layout in ("auto", "split") and _two_people(track):
        split = _split_tracks(track, n_frames, fps)
        if split:
            return "split", None, split
    single = [(t, faces[0][0] if faces else None) for t, faces in track]  # wajah terbesar
    found = sum(1 for _, x in single if x is not None)
    cam = _smooth_track(single, n_frames, fps) if found >= max(2, len(single) * 0.25) else None
    if cam is not None:
        return "face", cam, None
    return ("center" if layout == "face" else "blur"), None, None


ZOOM_PUNCH = 1.14   # perbesaran "Zoom hentak"


def _zoom(img: np.ndarray, z: float, cx: float = 0.5, cy: float = 0.42) -> np.ndarray:
    """Perbesar bagian tengah frame (sedikit di atas tengah, tempat wajah biasanya berada)."""
    import cv2
    H, W = img.shape[:2]
    w, h = int(round(W / z)), int(round(H / z))
    x0 = int(np.clip(cx * W - w / 2, 0, W - w))
    y0 = int(np.clip(cy * H - h / 2, 0, H - h))
    return cv2.resize(img[y0:y0 + h, x0:x0 + w], (W, H), interpolation=cv2.INTER_LINEAR)


def _zoom_plan(mode: str, words: list[dict], dur: float):
    """Fungsi waktu (detik video hasil) -> perbesaran, atau None bila tanpa zoom.
    halus : maju-mundur pelan (seperti kamera bernapas), siklus 8 detik
    hentak: berganti dekat/jauh di akhir kalimat atau jeda, seperti jump cut (paling cepat tiap 2,5 detik)"""
    import bisect
    if mode == "halus":
        return lambda t: 1.0 + 0.07 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 8.0))
    if mode != "hentak":
        return None
    switches, last = [], 0.0
    for a, b in zip(words, words[1:]):
        t = b["start"]
        boundary = a["word"].rstrip().endswith((".", "!", "?", ",")) or t - a["end"] > 0.3
        if (t - last >= 2.5 and boundary) or t - last >= 6.0:
            switches.append(t)
            last = t
    if not words:
        switches = [float(x) for x in np.arange(4.0, max(4.0, dur), 4.0)]
    return lambda t: ZOOM_PUNCH if bisect.bisect_right(switches, t) % 2 else 1.0


FILTERS = ("asli", "cerah", "hangat", "dingin", "hitamputih", "sinematik", "pudar")


def _grade_fn(name: str | None):
    """Filter warna untuk lapisan video (judul & subtitle tidak ikut berubah). None = warna asli."""
    import cv2
    if not name or name == "asli" or name not in FILTERS:
        return None
    x = np.arange(256, dtype=np.float32)
    lo, hi = 1 - x / 255, x / 255                    # bobot bayangan & bagian terang
    sat, vignette = 1.0, False
    if name == "cerah":
        b = g = r = (x - 128) * 1.1 + 128
        sat = 1.3
    elif name == "hangat":
        r, g, b = x * 0.96 + 16, x * 0.99 + 4, x * 0.9
        sat = 1.06
    elif name == "dingin":
        r, g, b = x * 0.92, x * 0.98 + 3, x * 0.95 + 18
    elif name == "hitamputih":
        b = g = r = (x - 128) * 1.12 + 128
        sat = 0.0
    elif name == "sinematik":                          # bayangan kehijauan-biru, bagian terang oranye
        s = 128 + (x - 128) * 1.15
        r, g, b = s - 10 * lo + 12 * hi, s + 3 * lo, s + 14 * lo - 10 * hi
        sat, vignette = 0.9, True
    else:  # pudar: hitam diangkat, warna lembut (kesan film lama)
        b = g = r = 28 + x * 0.8
        r, b = r + 6, b - 4
        sat = 0.75
    lut = np.clip(np.stack([b, g, r], axis=1), 0, 255).astype(np.uint8).reshape(256, 1, 3)
    mask = None
    if vignette:
        yy, xx = np.mgrid[0:OUT_H, 0:OUT_W].astype(np.float32)
        d = ((xx - OUT_W / 2) / (OUT_W * 0.75)) ** 2 + ((yy - OUT_H / 2) / (OUT_H * 0.7)) ** 2
        mask = np.repeat((np.clip(1 - 0.45 * d, 0.55, 1) * 255).astype(np.uint8)[..., None], 3, axis=2)

    def grade(img):
        out = cv2.LUT(img, lut)
        if sat != 1.0:
            gray = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            out = gray if sat == 0 else cv2.addWeighted(out, sat, gray, 1 - sat, 0)
        if mask is not None and out.shape == mask.shape:
            out = cv2.multiply(out, mask, scale=1 / 255)
        return out
    return grade


class FrameComposer:
    """Menyusun satu frame 1080x1920: tata letak + efek (zoom, filter) + judul + subtitle + watermark
    + progress bar. Dipakai oleh render penuh maupun pratinjau gaya, jadi hasil keduanya selalu sama."""

    def __init__(self, sw, sh, layout, cam, split, style, words, title, n_frames):
        self.sw, self.sh, self.layout, self.cam, self.split = sw, sh, layout, cam, split
        self.n_frames = max(1, n_frames)
        cap_style = dict(style)
        if layout == "split":
            cap_style["caption_pos"] = 0.5  # di garis tengah, tidak menutupi wajah
        self.cap = CaptionRenderer(words, cap_style) if style.get("captions", True) and words else None
        self.title_img = _title_image(title, style) if style.get("title_on", True) and title.strip() else None
        self.title_secs = float(style.get("title_secs", 0) or 0)  # 0 = sepanjang video
        self.title_y = int(OUT_H * float(style.get("title_pos", 0.11)))
        handle = (style.get("handle") or "").strip()
        self.handle_img = _handle_image(handle) if handle else None
        self.handle_y = int(OUT_H * (0.035 if style.get("handle_pos") == "atas" else 0.84))
        self.bar_on = style.get("progress_bar", True)
        self.bar_top = style.get("progress_pos") == "atas"
        self.bar_color = CAPTION_COLORS.get(style.get("caption_color", "kuning"), (255, 221, 0))[::-1]
        # zoom tidak dipakai pada tata letak dua orang (garis tengahnya ikut bergeser)
        self.zoom_mode = style.get("zoom", "tanpa") if layout != "split" else "tanpa"
        self.zoom = _zoom_plan(self.zoom_mode, words or [], self.n_frames / OUT_FPS)
        self.grade = _grade_fn(style.get("filter"))
        self.crop_w = min(sw, int(sh * 9 / 16))
        self.fg_h = int(OUT_W * sh / sw)
        self.half = OUT_H // 2
        self.split_cw = int(min(sw * 0.5, sh * OUT_W / self.half))
        self.split_ch = int(self.split_cw * self.half / OUT_W)

    def frame(self, f, i, t=None, zoom=None):
        """zoom: perbesaran paksa (dipakai pratinjau supaya efek zoom terlihat di satu frame)."""
        import cv2
        t = i / OUT_FPS if t is None else t
        sw, sh = self.sw, self.sh
        if self.layout in ("face", "center"):
            cx = self.cam[min(i, len(self.cam) - 1)] if self.cam is not None else 0.5
            x0 = int(np.clip(cx * sw - self.crop_w / 2, 0, sw - self.crop_w))
            out = cv2.resize(f[:, x0:x0 + self.crop_w], (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
        elif self.layout == "fill":
            scale = max(OUT_W / sw, OUT_H / sh)
            rw, rh = int(sw * scale + 0.5), int(sh * scale + 0.5)
            r = cv2.resize(f, (rw, rh), interpolation=cv2.INTER_LINEAR)
            xo, yo = (rw - OUT_W) // 2, (rh - OUT_H) // 2
            out = np.ascontiguousarray(r[yo:yo + OUT_H, xo:xo + OUT_W])
        elif self.layout == "split":  # dua orang: atas = kiri, bawah = kanan
            out = np.empty((OUT_H, OUT_W, 3), np.uint8)
            for k, (xs, ys) in enumerate(self.split):
                j = min(i, len(xs) - 1)
                x0 = int(np.clip(xs[j] * sw - self.split_cw / 2, 0, sw - self.split_cw))
                y0 = int(np.clip(ys[j] * sh - self.split_ch * 0.45, 0, sh - self.split_ch))
                part = f[y0:y0 + self.split_ch, x0:x0 + self.split_cw]
                out[k * self.half:(k + 1) * self.half] = cv2.resize(
                    part, (OUT_W, self.half), interpolation=cv2.INTER_LINEAR)
            out[self.half - 3:self.half + 3] = 0  # garis pemisah
        else:  # blur / hitam: video utuh di tengah, latar belakang buram atau hitam
            if self.layout == "hitam":
                out = np.zeros((OUT_H, OUT_W, 3), np.uint8)
            else:
                # digelapkan saat masih kecil (135x240), jauh lebih cepat daripada di ukuran penuh
                small = cv2.resize(f, (OUT_W // 8, OUT_H // 8), interpolation=cv2.INTER_AREA)
                small = cv2.convertScaleAbs(cv2.GaussianBlur(small, (0, 0), 6), alpha=0.55)
                out = cv2.resize(small, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
            y0 = (OUT_H - self.fg_h) // 2
            out[y0:y0 + self.fg_h] = cv2.resize(f, (OUT_W, self.fg_h), interpolation=cv2.INTER_AREA)

        z = zoom if zoom is not None else (self.zoom(t) if self.zoom else 1.0)
        if z > 1.001 and self.layout != "split":
            out = _zoom(out, z)
        if self.grade is not None:
            out = self.grade(out)
        if self.title_img is not None and (self.title_secs <= 0 or t < self.title_secs):
            _blend(out, self.title_img, (OUT_W - self.title_img.shape[1]) // 2, self.title_y)
        if self.handle_img is not None:
            _blend(out, self.handle_img, (OUT_W - self.handle_img.shape[1]) // 2, self.handle_y)
        if self.cap:
            self.cap.draw(out, t)
        if self.bar_on:
            bw = int(OUT_W * min(1.0, (i + 1) / self.n_frames))
            if self.bar_top:
                out[:14, :bw] = self.bar_color
            else:
                out[OUT_H - 14:OUT_H, :bw] = self.bar_color
        return out


_ENCODER = None  # "h264_nvenc" bila kartu NVIDIA bisa meng-encode video, selain itu "libx264" (CPU)


def video_encoder() -> str:
    """Encoder video untuk render. NVENC dicoba sekali; bila gagal (tanpa GPU/driver), pakai CPU."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = "libx264"
        if os.environ.get("NERO_CPU_ENCODE") != "1":
            try:
                r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                                    "-i", "color=c=black:s=256x256:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, **_popen_kwargs())
                if r.returncode == 0:
                    _ENCODER = "h264_nvenc"
            except Exception:
                pass
    return _ENCODER


def _video_codec_args(enc: str) -> list[str]:
    if enc == "h264_nvenc":  # kualitas setara crf ~20, dibatasi supaya file tetap wajar untuk diunggah
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "21", "-b:v", "0",
                "-maxrate", "16M", "-bufsize", "32M"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def clip_timeline(words, start: float, end: float, style: dict) -> tuple[list[tuple[int, int]], list[dict]]:
    """Bagian clip yang dipakai dalam nomor frame relatif terhadap `start` ([(k, m)] = frame k..m-1),
    dan kata-kata dengan waktu di video hasil (0 = awal). Dengan 'Hapus jeda' (style cut_pauses = detik),
    diam lebih lama dari batas itu dibuang; batas potongan dibulatkan ke frame supaya audio tetap sinkron."""
    fps = OUT_FPS
    n_full = max(1, int(max(0.5, end - start) * fps))
    ws = sorted((w for w in words if w["end"] > start and w["start"] < end), key=lambda w: w["start"])
    gap = float(style.get("cut_pauses", 0) or 0)
    spans = [(0.0, end - start)]
    if gap > 0 and ws:
        pad = min(0.12, gap / 2)          # sisa jeda di kiri-kanan potongan supaya tidak terdengar terpotong
        spans, a, last = [], ws[0]["start"] - start - pad, ws[0]["end"] - start
        for w in ws[1:]:
            s0 = w["start"] - start
            if s0 - last > gap:
                spans.append((a, last + pad))
                a = s0 - pad
            last = max(last, w["end"] - start)
        spans.append((a, last + 0.25))
    keep: list[tuple[int, int]] = []
    for a, b in spans:
        k, m = max(0, int(round(a * fps))), min(n_full, int(round(b * fps)))
        if m - k < 2:
            continue
        if keep and k <= keep[-1][1]:
            keep[-1] = (keep[-1][0], max(keep[-1][1], m))
        else:
            keep.append((k, m))
    keep = keep or [(0, n_full)]

    def remap(t):  # detik relatif sumber -> detik video hasil
        f, acc = t * fps, 0
        for k, m in keep:
            if f < k:
                return acc / fps
            if f <= m:
                return (acc + f - k) / fps
            acc += m - k
        return acc / fps

    rel = [{"start": round(remap(w["start"] - start), 3), "end": round(remap(w["end"] - start), 3),
            "word": w["word"]} for w in ws]
    return keep, rel


def render_clip(src: str, start: float, end: float, out_path: str, words: list[dict],
                style: dict, title: str = "", progress=None) -> str:
    global _ENCODER
    info = probe(src)
    dur = max(0.5, end - start)
    fps = OUT_FPS
    n_full = int(dur * fps)
    keep, rel = clip_timeline(words, start, end, style)
    full = keep == [(0, n_full)]
    n_frames = sum(m - k for k, m in keep)
    sw, sh = _decode_size(info)
    layout, cam, split = _plan_layout(src, start, dur, info, style, sw, sh, n_full, fps)
    if not full:  # jalur kamera hanya untuk frame yang dipakai
        idx = np.minimum(np.concatenate([np.arange(k, m) for k, m in keep]), n_full - 1)
        cam = cam[np.minimum(idx, len(cam) - 1)] if cam is not None else None
        split = [(xs[np.minimum(idx, len(xs) - 1)], ys[np.minimum(idx, len(ys) - 1)]) for xs, ys in split] \
            if split else None
    comp = FrameComposer(sw, sh, layout, cam, split, style, rel, title, n_frames)
    enc = video_encoder()
    try:
        _encode_clip(src, start, dur, keep, full, info, style, sw, sh, comp, n_frames, out_path, enc, progress)
    except RuntimeError:
        if enc != "h264_nvenc":
            raise
        _ENCODER = "libx264"  # NVENC sempat lolos uji tapi gagal di sini: ulangi dengan CPU
        _encode_clip(src, start, dur, keep, full, info, style, sw, sh, comp, n_frames, out_path, _ENCODER,
                     progress)
    # thumbnail
    try:
        run_ffmpeg(["-ss", f"{min(1.0, n_frames / fps / 2):.2f}", "-i", out_path, "-frames:v", "1",
                    "-vf", "scale=270:-2", out_path.rsplit(".", 1)[0] + ".jpg"])
    except Exception:
        pass
    return out_path


def _encode_clip(src, start, dur, keep, full, info, style, sw, sh, comp, n_frames, out_path, enc, progress):
    fps = OUT_FPS
    vf = f"fps={fps}"
    if not full:  # ambil frame k..m-1 dari tiap potongan lalu sambung (batas di tengah antar-frame)
        cond = "+".join(f"gte(t,{(k - 0.5) / fps:.4f})*lt(t,{(m - 0.5) / fps:.4f})" for k, m in keep)
        vf += f",select='{cond}',setpts=N/{fps}/TB"
    dec = subprocess.Popen(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", src, "-vf", f"{vf},scale={sw}:{sh}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_popen_kwargs())

    tmp_out = out_path + ".tmp.mp4"
    enc_cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(fps), "-i", "-"]
    if info.has_audio:
        norm = "loudnorm=I=-14:TP=-1.5:LRA=11" if style.get("loudnorm", True) else "anull"
        enc_cmd += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]
        if full:
            enc_cmd += ["-map", "0:v", "-map", "1:a:0", "-af", norm]
        else:  # potongan audio persis sama dengan potongan frame
            n = len(keep)
            g = [f"[1:a:0]asplit={n}" + "".join(f"[s{i}]" for i in range(n))] if n > 1 else []
            g += [(f"[s{i}]" if n > 1 else "[1:a:0]") + f"atrim=start={k / fps:.5f}:end={m / fps:.5f},"
                  f"asetpts=PTS-STARTPTS[a{i}]" for i, (k, m) in enumerate(keep)]
            g.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,{norm}[aout]")
            enc_cmd += ["-filter_complex", ";".join(g), "-map", "0:v", "-map", "[aout]"]
        enc_cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    enc_cmd += _video_codec_args(enc) + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-shortest", tmp_out]
    err_path = out_path + ".log"
    with open(err_path, "wb") as errf:
        proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=errf, **_popen_kwargs())
        frame_bytes = sw * sh * 3
        i, read, failed = 0, 0, None
        pending: deque = deque()
        # beberapa frame disusun bersamaan (OpenCV melepas GIL), urutan tulis tetap sama
        pool = ThreadPoolExecutor(max_workers=RENDER_THREADS)
        try:
            while i < n_frames:
                while read < n_frames and len(pending) < RENDER_THREADS * 2:
                    buf = dec.stdout.read(frame_bytes)
                    if len(buf) < frame_bytes:
                        n_frames = read
                        break
                    pending.append(pool.submit(comp.frame, np.frombuffer(buf, np.uint8).reshape(sh, sw, 3), read))
                    read += 1
                if not pending:
                    break
                proc.stdin.write(np.ascontiguousarray(pending.popleft().result()).data)
                i += 1
                if progress and i % 15 == 0:
                    progress(i / max(1, n_frames))
        except OSError as e:  # mis. encoder berhenti duluan (pipa putus): pesan galatnya ada di log
            failed = e
        finally:
            for fut in pending:
                fut.cancel()
            pool.shutdown(wait=True)
            try:
                proc.stdin.close()
            except Exception:
                pass
            dec.stdout.close()
            dec.wait()
            proc.wait()
    if failed or proc.returncode != 0 or not os.path.exists(tmp_out):
        with open(err_path, "rb") as f:
            raise RuntimeError("Render gagal: " + f.read().decode("utf-8", "ignore")[-600:])
    os.replace(tmp_out, out_path)
    try:
        os.remove(err_path)
    except OSError:
        pass


SAMPLE_WORDS = [{"start": 0.0, "end": 0.4, "word": "Contoh"}, {"start": 0.4, "end": 0.8, "word": "subtitle"},
                {"start": 0.8, "end": 1.2, "word": "keren"}]


_PREVIEW_CACHE: dict[tuple, tuple] = {}   # frame & tata letak pratinjau terakhir (kunci: video, waktu, tata letak)
_PREVIEW_LOCK = threading.Lock()


def _preview_source(src: str, t: float, style: dict):
    """Frame video pada detik t + rencana tata letaknya. Disimpan sementara, karena kartu gaya di halaman
    meminta banyak pratinjau dari frame yang sama (hanya gayanya yang berbeda)."""
    try:
        mtime = os.path.getmtime(src)
    except OSError:
        mtime = 0
    key = (src, mtime, round(t, 2), style.get("layout", "auto"))
    with _PREVIEW_LOCK:
        hit = _PREVIEW_CACHE.get(key)
    if hit:
        return hit
    info = probe(src)
    t = max(0.0, min(t, max(0.0, info.duration - 0.5)))
    sw, sh = _decode_size(info)
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", src,
                        "-frames:v", "1", "-vf", f"scale={sw}:{sh}", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kwargs())
    if len(r.stdout) < sw * sh * 3:
        raise RuntimeError("Tidak bisa mengambil frame dari video.")
    f = np.frombuffer(r.stdout[:sw * sh * 3], np.uint8).reshape(sh, sw, 3)
    win = min(4.0, max(0.5, info.duration - t))
    layout, cam, split = _plan_layout(src, t, win, info, style, sw, sh, 1, OUT_FPS)
    val = (f, sw, sh, layout, cam, split)
    with _PREVIEW_LOCK:
        if len(_PREVIEW_CACHE) >= 8:
            _PREVIEW_CACHE.pop(next(iter(_PREVIEW_CACHE)))
        _PREVIEW_CACHE[key] = val
    return val


def render_preview(src: str | None, t: float, words: list[dict], style: dict, title: str = "",
                   width: int = OUT_W // 2) -> bytes:
    """Satu frame contoh (JPEG 9:16, lebar `width`) dengan gaya ini, tanpa merender video."""
    import cv2
    if src:
        f, sw, sh, layout, cam, split = _preview_source(src, t, style)
    else:  # belum ada video: latar gradasi
        sw, sh = 1920, 1080
        gx = np.linspace(0, 1, sw, dtype=np.float32)[None, :, None]
        gy = np.linspace(0, 1, sh, dtype=np.float32)[:, None, None]
        f = np.concatenate([np.broadcast_to(90 + 120 * gx, (sh, sw, 1)),
                            np.broadcast_to(60 + 80 * gy, (sh, sw, 1)),
                            np.broadcast_to(140 - 60 * gx, (sh, sw, 1))], axis=2).astype(np.uint8)
        lay = style.get("layout", "auto")
        layout, cam, split = ("blur" if lay in ("auto", "face", "split") else lay), None, None
    rel = [{"start": w["start"] - t, "end": w["end"] - t, "word": w["word"]} for w in words] or SAMPLE_WORDS
    tt = (rel[1] if len(rel) > 1 else rel[0])["start"] + 0.1  # kata ke-2 sedang disorot
    comp = FrameComposer(sw, sh, layout, cam, split, style, rel, title, 100)
    # efek zoom ditampilkan pada keadaan "dekat" supaya terlihat bedanya
    z = {"hentak": ZOOM_PUNCH, "halus": 1.05}.get(comp.zoom_mode)
    out = comp.frame(f, 34, t=tt, zoom=z)
    small = cv2.resize(out, (width, int(width * OUT_H / OUT_W)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise RuntimeError("Gagal membuat gambar pratinjau.")
    return buf.tobytes()


def clip_words_text(segments, start: float, end: float) -> str:
    """Teks subtitle sebuah clip (kata-kata transkrip di rentang itu), untuk diedit pengguna."""
    return " ".join(w["word"] for s in segments for w in s["words"] if w["end"] > start and w["start"] < end)


def edit_words(segments, start: float, end: float, text: str) -> int:
    """Ganti kata transkrip di rentang clip dengan teks hasil koreksi pengguna (mengubah `segments`).
    Kata yang sama tetap memakai waktunya; kata yang diganti/ditambah mengisi waktu kata lama di posisi itu,
    dibagi menurut panjang hurufnya. Hasil: banyaknya kata yang berubah."""
    import difflib
    pos = [(si, wi) for si, s in enumerate(segments) for wi, w in enumerate(s["words"])
           if w["end"] > start and w["start"] < end]
    new = text.split()
    if not pos:
        raise ValueError("Tidak ada kata transkrip di rentang clip ini.")
    if not new:
        raise ValueError("Teks subtitle tidak boleh kosong.")
    old = [segments[si]["words"][wi] for si, wi in pos]
    placed: list[tuple[int, dict]] = []   # (nomor segmen, kata baru)
    changed = 0

    def spread(tokens, t0, t1, seg):
        t1 = max(t1, t0 + 0.05 * len(tokens))
        total = sum(len(t) for t in tokens) or 1
        t = t0
        for tok in tokens:
            d = (t1 - t0) * len(tok) / total
            placed.append((seg, {"start": round(t, 2), "end": round(t + d, 2), "word": tok}))
            t += d

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=[w["word"] for w in old], b=new,
                                                       autojunk=False).get_opcodes():
        if tag == "equal":
            placed += [(pos[i][0], dict(old[i])) for i in range(i1, i2)]
        elif tag == "replace":
            spread(new[j1:j2], old[i1]["start"], old[i2 - 1]["end"], pos[i1][0])
            changed += max(i2 - i1, j2 - j1)
        elif tag == "insert":
            if placed:  # sisipan memakai separuh akhir waktu kata sebelumnya
                seg, prev = placed[-1]
                mid = round((prev["start"] + prev["end"]) / 2, 2)
                t1, prev["end"] = prev["end"], mid
                spread(new[j1:j2], mid, t1, seg)
            else:       # sisipan di paling awal: tepat sebelum kata pertama
                spread(new[j1:j2], max(0.0, old[0]["start"] - 0.3 * (j2 - j1)), old[0]["start"], pos[0][0])
            changed += j2 - j1
        else:  # delete
            changed += i2 - i1

    gone = set(pos)
    first = {}
    for si, wi in pos:
        first.setdefault(si, wi)
    by_seg: dict[int, list] = {}
    for si, w in placed:
        by_seg.setdefault(si, []).append(w)
    for si in sorted(first):
        words = segments[si]["words"]
        before = [w for wi, w in enumerate(words) if wi < first[si] and (si, wi) not in gone]
        after = [w for wi, w in enumerate(words) if wi > first[si] and (si, wi) not in gone]
        segments[si]["words"] = before + by_seg.get(si, []) + after
        segments[si]["text"] = " ".join(w["word"] for w in segments[si]["words"])
    return changed


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


# --------------------------------------------------------------------------
# 6. Tiru gaya dari clip referensi (tanpa AI): baca frame-nya, tebak pengaturan gaya
# --------------------------------------------------------------------------
_HUE_NAMES = (("merah", 0), ("oranye", 33), ("kuning", 52), ("hijau", 112), ("toska", 168), ("biru", 195),
              ("ungu", 268), ("pink", 318), ("merah", 360))
# dikalibrasi dengan clip hasil Clip Maker sendiri (gaya diketahui)
_LINE_TO_FONT = 0.78      # tinggi huruf kapital terdeteksi ≈ 0,78 × ukuran font (untuk Impact; font lain ±15%)
_POS_OFFSET = 0.0         # selisih pusat teks terdeteksi terhadap caption_pos (porsi tinggi layar)
ANALYZE_WIDTH = 320       # lebar frame saat membaca gaya (semua ambang dikalibrasi untuk lebar ini)
# porsi kolom huruf yang hanya setinggi huruf 'x': HURUF BESAR ~0,1-0,3, huruf kecil biasa ~0,6-0,7.
# Di antaranya tidak pasti (mis. teks kecil, atau Impact huruf kecil yang huruf 'x'-nya hampir setinggi kapital)
_UPPER_MAX_X, _LOWER_MIN_X = 0.30, 0.50


def _runs(mask, gap=0, min_len=1) -> list[tuple[int, int]]:
    """Rentang [a, b) yang bernilai True; celah sampai `gap` digabung."""
    idx = np.flatnonzero(mask)
    out = []
    if not len(idx):
        return out
    a = prev = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - prev > gap + 1:
            if prev + 1 - a >= min_len:
                out.append((a, prev + 1))
            a = i
        prev = i
    if prev + 1 - a >= min_len:
        out.append((a, prev + 1))
    return out


def _read_frames(path, info: VideoInfo, fps: float, secs: float, width: int) -> np.ndarray:
    h = int(round(info.height * width / info.width / 2)) * 2
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", path, "-t", f"{secs:.1f}",
                        "-vf", f"fps={fps},scale={width}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_popen_kwargs())
    n = width * h * 3
    return np.frombuffer(r.stdout[: len(r.stdout) // n * n], np.uint8).reshape(-1, h, width, 3)


def _text_masks(frames) -> np.ndarray:
    """Piksel 'teks bergaris tepi': terang (putih / warna mencolok) yang menempel piksel sangat gelap.
    Cocok untuk subtitle ber-outline hitam dan teks gelap di kotak terang."""
    import cv2
    k = np.ones((5, 5), np.uint8)
    out = np.empty(frames.shape[:3], np.uint8)
    for i, f in enumerate(frames):
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        s, v = hsv[..., 1], hsv[..., 2]
        bright = (v >= 185) & ((s <= 70) | (s >= 140))
        near_dark = cv2.dilate((v <= 60).astype(np.uint8), k) > 0
        out[i] = bright & near_dark
    return out


def _caption_masks(frames) -> np.ndarray:
    """Seperti _text_masks, tetapi hanya bidang terang seukuran huruf yang terpisah satu sama lain
    (isi huruf subtitle dikelilingi outline hitam). Bidang terang besar, mis. kertas bertulisan di video
    aslinya atau kotak judul putih, tidak ikut."""
    import cv2
    H, W = frames.shape[1:3]
    k = np.ones((5, 5), np.uint8)
    out = np.empty(frames.shape[:3], np.uint8)
    for i, f in enumerate(frames):
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        s, v = hsv[..., 1], hsv[..., 2]
        bright = ((v >= 185) & ((s <= 70) | (s >= 140))).astype(np.uint8)
        _, lab, st, _ = cv2.connectedComponentsWithStats(bright, connectivity=4)
        ok = ((st[:, cv2.CC_STAT_HEIGHT] <= 0.1 * H) & (st[:, cv2.CC_STAT_HEIGHT] >= 0.014 * H)
              & (st[:, cv2.CC_STAT_WIDTH] <= 0.4 * W) & (st[:, cv2.CC_STAT_AREA] >= 0.00012 * H * W))
        ok[0] = False
        near_dark = cv2.dilate((v <= 45).astype(np.uint8), k) > 0
        out[i] = ok[lab] & near_dark
    return out


def _split_gaps(gaps, med: float) -> float:
    """Batas celah antarkata: dua kelompok celah (antarhuruf kecil, antarkata besar) dipisah dengan cara Otsu.
    Bila tidak terlihat dua kelompok, pakai perkiraan 0,22 × tinggi baris."""
    g = np.sort(np.asarray(gaps, float))
    g = g[g < 0.6 * med]   # celah sangat lebar = jarak ke potongan lain, bukan antarkata
    if len(g) < 6:
        return 0.22 * med
    n, cs = len(g), np.cumsum(g)
    i = np.arange(1, n)
    m_lo, m_hi = cs[:-1] / i, (cs[-1] - cs[:-1]) / (n - i)
    score = i * (n - i) * (m_hi - m_lo) ** 2
    score[g[1:] == g[:-1]] = -1                 # potong hanya di antara nilai yang berbeda
    k = int(np.argmax(score))
    lo, hi = m_lo[k], m_hi[k]
    if hi < 1.8 * max(lo, 1.0):
        return 0.22 * med
    # dibatasi: tanpa celah antarkata (1 kata per tampilan) Otsu bisa memotong di antara huruf
    return float(np.clip((g[k] + g[k + 1]) / 2, 0.22 * med, 0.38 * med))


def _hue_name(deg: float) -> str:
    return min(_HUE_NAMES, key=lambda x: abs(x[1] - deg))[0]


def analyze_reference_style(path: str, fps: float = 3.0, secs: float = 40.0) -> dict:
    """Tebak gaya video pendek dari clip contoh, tanpa AI.
    Hasil: {"style": {kunci gaya yang terdeteksi}, "notes": [catatan untuk pengguna], "seconds": durasi dibaca,
            "debug": angka mentah untuk kalibrasi}. Kunci yang tidak yakin tidak diisi (pengaturan lama dipakai)."""
    import cv2
    info = probe(path)
    if info.width > info.height * 0.9:
        raise RuntimeError("clip referensi bukan video vertikal (9:16), gayanya tidak bisa ditiru")
    frames = _read_frames(path, info, fps, secs, ANALYZE_WIDTH)
    if len(frames) < 6:
        raise RuntimeError("video referensi terlalu pendek atau tidak bisa dibaca")
    T, H, W = frames.shape[:3]
    M = _text_masks(frames)
    ink = M.mean(axis=2)                      # (T, H): porsi piksel teks per baris
    on = ink > 0.03
    style, notes, dbg = {}, [], {}
    extra = {"caption_band": None, "caption_times": [], "title_band": None}   # untuk pembacaan lanjutan oleh AI
    excluded = np.zeros(H, bool)              # baris berisi teks, diabaikan saat menilai tata letak

    # ---- judul: teks diam di bagian atas pada detik-detik awal
    w0 = max(3, int(2.5 * fps))
    pres0 = on[:w0].mean(axis=0)
    xor0 = (M[1:w0] ^ M[:w0 - 1]).mean(axis=2).mean(axis=0)
    rel0 = xor0 / (ink[:w0].mean(axis=0) + 1e-4)
    still = (pres0 >= 0.8) & (rel0 < 0.25)
    still[int(H * 0.55):] = False
    title = max(_runs(still, gap=4, min_len=max(4, H // 90)), key=lambda r: r[1] - r[0], default=None)
    if title:
        ta, tb = title
        excluded[ta:tb] = True
        extra["title_band"] = (ta / H, tb / H)
        shown = on[:, ta:tb].mean(axis=1) > 0.35
        gone = next((t for t in range(w0, T - 1) if not shown[t] and not shown[t + 1]), None)
        if gone is None:
            style["title_secs"] = 0
        else:
            secs_shown = gone / fps
            style["title_secs"] = 3 if secs_shown <= 4.2 else 5 if secs_shown <= 7.5 else 0
        style["title_on"] = True
        # warna kotak judul: baris tepat di atas & di bawah tulisan (bagian kotak tanpa huruf)
        tf = [t for t in range(T) if shown[t]][:12]
        cols = np.flatnonzero(M[tf, ta:tb].max(axis=(0, 1)))
        pad = [y for y in list(range(ta - 5, ta - 1)) + list(range(tb + 2, tb + 6)) if 0 <= y < H]
        if len(cols) and pad:
            area = frames[tf][:, pad, cols[0]:cols[-1] + 1].reshape(1, -1, 3)
            hsv = cv2.cvtColor(np.ascontiguousarray(area), cv2.COLOR_BGR2HSV)[0]
            h, s, v = (float(np.median(hsv[:, i])) for i in range(3))
            dbg["title_hsv"] = (h, s, v, ta, tb)
            if v >= 190 and s <= 60:
                style["title_bg"] = "putih"
            elif v >= 160 and s >= 110 and 18 <= h <= 35:
                style["title_bg"] = "kuning"
            elif v <= 90:
                style["title_bg"] = "hitam"
    else:
        style["title_on"] = False

    # ---- subtitle: pita teks yang isinya sering berganti. Piksel teks yang hampir selalu ada
    # (judul, tulisan di video aslinya) dibuang dulu supaya tidak ikut terhitung.
    C = _caption_masks(frames)
    Dm = C & ~(C.mean(axis=0) >= 0.5)
    dink = Dm.mean(axis=2)
    presence = (dink > 0.03).mean(axis=0)
    rel = (Dm[1:] ^ Dm[:-1]).mean(axis=2).mean(axis=0) / (dink.mean(axis=0) + 1e-4)
    cand = (presence > 0.2) & ~excluded
    cand[: int(H * 0.06)] = False
    cand[int(H * 0.97):] = False
    bands = []
    for a, b in _runs(cand, gap=3, min_len=max(4, H // 80)):
        pr = presence[a:b]
        if float(np.average(rel[a:b], weights=pr)) >= 0.3:
            bands.append((float(pr.sum()), a, b))
    strong = [x for x in bands if x[0] >= 0.5 * max(bands)[0]] if bands else []
    n_lines = 0.0
    for _, sa, sb in strong:
        per = [len(_runs(Dm[t, sa:sb].mean(axis=1) > 0.03, gap=1, min_len=3)) for t in range(T)]
        per = [n for n in per if n]
        n_lines += float(np.median(per)) if per else 0.0
    dbg["bands"] = (len(strong), n_lines)
    if n_lines >= 3:  # subtitle paling banyak 2 baris; lebih dari itu tulisan di video (paragraf)
        notes.append("Banyak tulisan bergerak di video ini (bukan subtitle biasa), pengaturan subtitle tidak diubah.")
        bands = []
    if bands:
        _, a, b = max(bands)
        # pita diperlebar ~1 baris: kelompok yang terbungkus 2 baris & huruf tinggi yang jarang muncul ikut terbaca
        ext = max(3, int(0.8 * (b - a)))
        a0, b0 = a, b
        a, b = max(0, a - ext), min(H, b + ext)
        if excluded[a:a0].any():
            a = a0 - int(np.argmax(excluded[a:a0][::-1]))
        if excluded[b0:b].any():
            b = b0 + int(np.argmax(excluded[b0:b]))
        excluded[a:b] = True
        per_frame = []
        for t in range(T):
            m = Dm[t, a:b]
            per_frame.append((t, m, _runs(m.mean(axis=1) > 0.03, gap=1, min_len=3)))
        all_h = [lb - la for _, _, ls in per_frame for la, lb in ls]
        med = float(np.median(all_h)) if all_h else 0.0
        found = []                                # (frame, mask pita, baris [(atas, bawah, garis dasar)])
        for t, m, lines in per_frame:
            # buang garis bising (terlalu tipis) dan gabungan subtitle + tulisan video (terlalu tinggi)
            lines = [(la, lb) for la, lb in lines if 0.6 * med <= lb - la <= 1.7 * med]
            if lines:
                found.append((t, m, [(la, lb, la + int(np.flatnonzero(
                    m[la:lb].mean(axis=1) >= 0.35 * m[la:lb].mean(axis=1).max())[-1]))  # garis dasar
                    for la, lb in lines]))
        # celah antarhuruf vs antarkata dipisah dari sebaran celah di clip ini sendiri (tiap font berbeda)
        gaps = []
        for _, m, ls in found:
            for la, lb, _ in ls:
                ink = _runs(m[la:lb].max(axis=0) > 0)
                gaps += [s2 - e1 for (_, e1), (s2, _) in zip(ink, ink[1:])]
        word_gap = _split_gaps(gaps, med)
        lines_h = [base + 1 - la for _, _, ls in found for la, _, base in ls]
        counts, centers, word_h, col_all = [], [], [], []
        for t, m, ls in found:
            nw, used = 0, []
            for la, lb, base in ls:
                sub = m[la:base + 1] > 0
                col_h = sub.shape[0] - sub.argmax(axis=0)       # tinggi huruf per kolom dari garis dasar
                segs = []
                for sa, sb in _runs(m[la:lb].max(axis=0) > 0, gap=int(word_gap), min_len=2):
                    hs = col_h[sa:sb][sub[:, sa:sb].any(axis=0)]
                    if sb - sa >= 0.25 * med and len(hs) and hs.max() >= 0.45 * med:   # bukan bintik kecil
                        segs.append((sa, sb, hs))
                # subtitle rata tengah: ambil rangkaian kata di tengah, buang potongan tulisan video di pinggir
                groups, cur = [], []
                for sg in segs:
                    if cur and sg[0] - cur[-1][1] > 3 * word_gap:
                        groups.append(cur)
                        cur = []
                    cur.append(sg)
                if cur:
                    groups.append(cur)
                mid = [g for g in groups if abs((g[0][0] + g[-1][1]) / 2 - W / 2) <= 0.12 * W]
                if not mid:
                    continue
                used.append((la, lb))
                for sa, sb, hs in min(mid, key=lambda g: abs((g[0][0] + g[-1][1]) / 2 - W / 2)):
                    nw += 1
                    word_h.append(float(hs.max()))   # huruf tertinggi kata itu
                    col_all.append(hs)
            if nw:
                counts.append(nw)
                centers.append(a + (used[0][0] + used[-1][1]) / 2)
        if counts:
            extra["caption_band"] = (a / H, b / H)
            extra["caption_times"] = [round(t / fps, 2) for t, _, _ in found]
            # tinggi kapital: kata ber-huruf tinggi (bukan kata huruf kecil saja); kata kunci yang dibesarkan sedikit
            cap = float(np.percentile(word_h, 80))
            # huruf kecil: kebanyakan kolom huruf hanya setinggi huruf 'x'; HURUF BESAR: setinggi kapital
            r = np.concatenate(col_all) / cap
            xzone = float(np.mean((r >= 0.62) & (r <= 0.88)))
            dbg["sub"] = dict(band=(a, b), med=med, word_gap=round(word_gap, 1), cap=cap, xz=round(xzone, 2),
                              lines=np.percentile(lines_h, [10, 50, 90]).tolist(), counts=np.bincount(counts).tolist())
            style["captions"] = True
            style["caption_size"] = int(np.clip(round(cap * 1920 / H / _LINE_TO_FONT / 2) * 2, 60, 120))
            style["caption_pos"] = round(float(np.clip(np.median(centers) / H + _POS_OFFSET, 0.5, 0.82)), 2)
            # pengaturan = jumlah kata MAKSIMUM; tampilan sering lebih sedikit (kata panjang, akhir kalimat),
            # jadi pakai jumlah terbesar yang cukup sering muncul
            hist = np.bincount(np.clip(counts, 0, 4), minlength=5)[1:]
            style["caption_words"] = int(max(k + 1 for k in range(4) if hist[k] >= 0.35 * hist.max()))
            if xzone <= _UPPER_MAX_X:
                style["caption_upper"] = True
            elif xzone >= _LOWER_MIN_X:
                style["caption_upper"] = False
            else:
                notes.append("HURUF BESAR atau huruf kecil tidak bisa dipastikan, pengaturan itu tidak diubah.")
            # warna sorotan: warna mencolok yang paling sering di antara piksel teks
            px = np.concatenate([cv2.cvtColor(frames[t, a:b], cv2.COLOR_BGR2HSV)[Dm[t, a:b] > 0]
                                 for t in range(0, T, 2)] or [np.zeros((0, 3), np.uint8)])
            vivid = px[(px[:, 1] >= 140) & (px[:, 2] >= 150)]
            style["caption_base"], style["caption_color"] = "putih", "putih"
            if len(px) and len(vivid) >= 0.06 * len(px):
                per_name: dict[str, int] = {}
                for hb, n in enumerate(np.bincount((vivid[:, 0].astype(int) * 2) // 10, minlength=36)):
                    name = _hue_name(hb * 10 + 5)
                    per_name[name] = per_name.get(name, 0) + int(n)
                ranked = sorted(per_name.items(), key=lambda kv: -kv[1])
                style["caption_color"] = ranked[0][0]
                # hampir semua huruf berwarna (dan lebih dari 1 kata per tampilan): warna dasarnya bukan putih
                if len(vivid) >= 0.7 * len(px) and style["caption_words"] > 1:
                    style["caption_base"] = ranked[0][0]
                    if len(ranked) > 1 and ranked[1][1] >= 0.15 * len(vivid):
                        style["caption_color"] = ranked[1][0]
            box = _highlight_box(frames, [t for t, _, _ in found], a, b, med)
            dbg["box"] = box
            if box:
                style["caption_highlight"], style["caption_color"] = "kotak", box
            if presence[a:b].max() < 0.35:
                notes.append("Subtitle hanya sesekali terlihat, hasil subtitle mungkin kurang tepat.")
    else:
        notes.append("Subtitle bergaris tepi tidak terdeteksi, pengaturan subtitle tidak diubah.")

    # ---- progress bar: garis di tepi bawah/atas yang memanjang seiring waktu
    def growing(row):
        pix = frames[:, row].astype(int)
        c0 = pix[-1, 2]
        same = np.abs(pix - c0).sum(axis=2) < 70
        lens = np.where(same.all(axis=1), W, np.argmin(same, axis=1))
        if lens[-1] < 0.12 * W or lens[-1] - lens[0] < 0.1 * W or np.ptp(lens) == 0:
            return False
        return float(np.corrcoef(np.arange(T), lens)[0, 1]) > 0.9
    style["progress_bar"] = bool(growing(H - 2) or growing(1))

    # ---- tata letak
    gray = frames.mean(axis=3, dtype=np.float32)
    # garis pemisah dua orang: baris gelap rata di tengah yang jelas lebih gelap dari sekitarnya
    # (pada video yang memang gelap, baris tengah yang gelap saja bukan tanda pemisah)
    row_mean, row_std = gray.mean(axis=2), gray.std(axis=2)
    hit = np.zeros(T, bool)
    for y in range(H // 2 - 3, H // 2 + 3):
        near = np.maximum(row_mean[:, max(0, y - 6)], row_mean[:, min(H - 1, y + 6)])
        hit |= (row_mean[:, y] < 45) & (row_std[:, y] < 20) & (near > row_mean[:, y] + 25)
    divider = float(hit.mean())
    both, single = 0, 0
    samples = np.linspace(0, T - 1, min(10, T)).astype(int)
    try:
        yn = cv2.FaceDetectorYN.create(os.path.join(APP_DIR, "models", "face_yunet.onnx"), "", (W, H), 0.6, 0.3, 20)
        for t in samples:
            _, faces = yn.detect(np.ascontiguousarray(frames[t]))
            faces = [] if faces is None else [f for f in faces if f[2] >= 0.08 * W]
            cys = [(f[1] + f[3] / 2) / H for f in faces]
            if any(c < 0.45 for c in cys) and any(c > 0.55 for c in cys):
                both += 1
            if any(f[2] >= 0.15 * W for f in faces):
                single += 1
    except Exception:
        pass
    # video utuh + latar blur / bar hitam: garis tepi lurus selebar layar di atas & bawah video,
    # di atasnya latar lebih gelap/buram (selisih ke bawah positif), di bawahnya kebalikannya
    d = np.diff(gray[samples], axis=1)                                 # (n, H-1, W)
    up = (d > 4).mean(axis=(0, 2))
    down = (d < -4).mean(axis=(0, 2))
    lap = np.array([np.abs(cv2.Laplacian(g, cv2.CV_32F)).mean(axis=1) for g in gray[samples]]).mean(axis=0)
    keep = ~excluded
    tops = [y for y in range(int(H * 0.12), int(H * 0.45)) if keep[y] and up[y] >= 0.6]
    blur = None
    for y1 in tops:
        # tepi bawah = cerminan tepi atas (video diletakkan di tengah); boleh tertutup subtitle
        win = range(max(0, H - 8 - y1), min(H - 1, H + 5 - y1))
        if not any(down[y] >= 0.3 or not keep[y] for y in win):
            continue
        y2 = max(win, key=lambda y: down[y])
        if 0.2 * H <= y2 - y1 <= 0.65 * H:
            inside = lap[y1 + 3: y2 - 2][keep[y1 + 3: y2 - 2]].mean()
            outside = np.concatenate([lap[: y1 - 2][keep[: y1 - 2]], lap[y2 + 3:][keep[y2 + 3:]]]).mean()
            if outside < 0.5 * inside:
                blur = (y1, y2)
                break
    dbg["layout"] = dict(tops=tops, maxup=round(float(up[int(H * .12):int(H * .45)].max()), 2),
                         maxdown=round(float(down[int(H * .55):int(H * .88)].max()), 2),
                         divider=divider, both=both, single=single, blur=blur)
    if divider >= 0.6 or both >= max(2, 0.5 * len(samples)):
        style["layout"] = "split"
    elif blur:
        y1, y2 = blur
        rows = np.r_[0:max(1, y1 - 2), min(H - 1, y2 + 3):H]
        rows = rows[keep[rows]] if keep[rows].any() else rows
        # latar hitam polos (bukan blur): hampir semua piksel di luar video sangat gelap
        dark = float(np.median(gray[samples][:, rows]))
        dbg["layout"]["outside"] = round(dark, 1)
        style["layout"] = "hitam" if dark < 16 else "blur"
    elif single >= 0.4 * len(samples):
        style["layout"] = "face"
    else:
        style["layout"] = "center"

    # ---- warna: video hitam-putih terbaca pasti; warna lain hanya dicatat (dinilai AI bila ada)
    rows = np.flatnonzero(keep[: H - 6])
    hsv = np.stack([cv2.cvtColor(frames[t], cv2.COLOR_BGR2HSV) for t in samples])[:, rows]
    bgr = frames[samples][:, rows].astype(np.float32)
    color = {"sat": round(float(hsv[..., 1].mean()), 1),
             "warm": round(float((bgr[..., 2] - bgr[..., 0]).mean()), 1),
             "bright": round(float(hsv[..., 2].mean()), 1)}
    dbg["color"] = color
    if color["sat"] < 14:
        style["filter"] = "hitamputih"

    # ---- zoom: perbesaran mendadak (jump cut) atau maju-mundur pelan
    motion = _motion_stats(frames, keep, fps)
    dbg["motion"] = motion
    if motion["jumps_per_min"] >= 3:
        style["zoom"] = "hentak"
    elif motion["slow_zoom"]:
        style["zoom"] = "halus"
    elif motion["measured"]:
        style["zoom"] = "tanpa"

    notes.append("Musik, b-roll, stiker, dan emoji tidak ikut ditiru.")
    return {"style": style, "notes": notes, "seconds": round(T / fps, 1), "debug": dbg,
            "measure": {**extra, "color": color, "motion": motion}}


def _highlight_box(frames, times, a, b, line_h) -> str | None:
    """Kata yang disorot dengan kotak berwarna? Kotak = bidang warna mencolok seukuran kata dengan tepi atas &
    bawah yang lurus penuh. Huruf berwarna biasa tidak begitu: di baris tepinya ada celah antarhuruf (garis tepi
    hitam). Hasil: nama warna kotak, atau None."""
    import cv2
    if not times or line_h <= 0:
        return None
    hits, hues = 0, []
    sample = times[::2] or times
    for t in sample:
        hsv = cv2.cvtColor(np.ascontiguousarray(frames[t, a:b]), cv2.COLOR_BGR2HSV)
        viv = (hsv[..., 1] >= 110) & (hsv[..., 2] >= 110)
        if not viv.any():
            continue
        # hanya warna yang paling banyak: bintik warna-warni video di sekitarnya tidak ikut menempel ke kotak
        hue = hsv[..., 0].astype(int)
        dom = int(np.argmax(np.bincount(hue[viv] // 6, minlength=31))) * 6 + 3
        viv = (viv & (np.minimum(np.abs(hue - dom), 180 - np.abs(hue - dom)) <= 12)).astype(np.uint8)
        white = (hsv[..., 1] <= 60) & (hsv[..., 2] >= 200)
        n, lab, st, _ = cv2.connectedComponentsWithStats(viv, connectivity=8)
        found = None
        # 1) kotak utuh (warna terang dengan tulisan gelap, atau huruf kecil): tepi atas & bawah lurus penuh.
        #    Lebarnya minimal 1,35 x tinggi supaya satu huruf tebal (mis. "E" berwarna) tidak dikira kotak
        for k in range(1, n):
            x, y, w, h, area = (int(v) for v in st[k])
            # isi kotak berlubang karena tulisan di dalamnya, jadi batas isinya rendah; yang menentukan tepinya
            if not (0.8 * line_h <= h <= 2.4 * line_h and w >= 1.35 * h and area >= 0.2 * w * h):
                continue
            inner = viv[y:y + h, x + int(0.15 * w): x + w - int(0.15 * w)]   # tanpa sudut membulat
            band = max(1, int(0.18 * h))   # baris tepi terbaik di atas & bawah (tepi kotak hanya beberapa piksel)
            top = max(inner[r].mean() for r in range(0, band))
            bottom = max(inner[r].mean() for r in range(h - band, h))
            if top >= 0.85 and bottom >= 0.85:
                found = lab[y:y + h, x:x + w] == k, (y, x, h, w)
                break
        # 2) kotak warna gelap terpotong-potong oleh huruf putih bergaris tepi: gabungkan potongan yang
        #    berdekatan, lalu periksa sisi kiri-kanan penuh dan ada tulisan putih di dalamnya
        #    (kata berwarna biasa tidak pernah berisi huruf putih)
        if found is None:
            parts = sorted((int(st[k][0]), int(st[k][1]), int(st[k][2]), int(st[k][3])) for k in range(1, n)
                           if st[k][3] >= 0.5 * line_h and st[k][4] >= 4)
            groups, cur = [], []
            for p in parts:
                if cur and p[0] - max(q[0] + q[2] for q in cur) > 0.3 * line_h:
                    groups.append(cur)
                    cur = []
                cur.append(p)
            groups.append(cur)
            for g in groups:
                if len(g) < 2:
                    continue
                x0, y0 = min(p[0] for p in g), min(p[1] for p in g)
                x1, y1 = max(p[0] + p[2] for p in g), max(p[1] + p[3] for p in g)
                w, h = x1 - x0, y1 - y0
                if not (0.8 * line_h <= h <= 2.4 * line_h and w >= 1.35 * h):
                    continue
                reg, mid = viv[y0:y1, x0:x1], slice(int(0.25 * h), max(int(0.25 * h) + 1, int(0.75 * h)))
                side = max(1, int(0.06 * w))
                ends = min(reg[int(0.2 * h):int(0.8 * h) or 1, :side].mean(), reg[int(0.2 * h):int(0.8 * h) or 1, -side:].mean())
                if 0.25 <= reg.mean() <= 0.85 and white[y0:y1, x0:x1][mid].mean() >= 0.12 and ends >= 0.7:
                    found = reg > 0, (y0, x0, h, w)
                    break
        if found is not None:
            m, (y, x, h, w) = found
            hits += 1
            hues.append(hsv[y:y + h, x:x + w][m][:, 0])
    if hits < max(2, 0.35 * len(sample)):
        return None
    ang = np.concatenate(hues).astype(np.float64) * (2 * np.pi / 180)   # rata-rata melingkar: merah ada di 0 & 180
    deg = math.degrees(math.atan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360
    return _hue_name(deg)


def _motion_stats(frames, keep_rows, fps) -> dict:
    """Gerak kamera antar-frame (dibaca dengan titik fitur ORB, baris berisi teks diabaikan):
    jumps_per_min  : perbesaran mendadak >= 6% (efek 'zoom hentak' / punch-in)
    cuts_per_min   : pergantian adegan
    slow_zoom      : perbesaran pelan yang konsisten (efek 'zoom halus')
    measured       : cukup frame yang bisa dibaca untuk menyimpulkan 'tanpa zoom'"""
    import cv2
    T, H, W = frames.shape[:3]
    out = {"jumps_per_min": 0.0, "cuts_per_min": 0.0, "slow_zoom": False, "measured": False}
    if T < 6:
        return out
    mask = np.zeros((H, W), np.uint8)
    mask[keep_rows] = 255
    gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    orb = cv2.ORB_create(nfeatures=400, fastThreshold=12)
    feats = [orb.detectAndCompute(g, mask) for g in gray]
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    def scale(a, b):
        (ka, da), (kb, db) = feats[a], feats[b]
        if da is None or db is None or len(ka) < 25 or len(kb) < 25:
            return None
        m = bf.match(da, db)
        if len(m) < 20:
            return None
        pa = np.float32([ka[x.queryIdx].pt for x in m])
        pb = np.float32([kb[x.trainIdx].pt for x in m])
        M, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if M is None or inl is None or int(inl.sum()) < max(15, 0.3 * len(m)):
            return None
        return float(np.hypot(M[0, 0], M[1, 0]))

    rows = np.flatnonzero(keep_rows)
    jumps = cuts = readable = 0
    shot_start, drift = 0, []
    for t in range(T - 1):
        diff = float(cv2.absdiff(gray[t][rows], gray[t + 1][rows]).mean())
        s = scale(t, t + 1)
        if s is not None:
            readable += 1
        if diff > 8 and s is not None and abs(math.log(s)) > 0.06:
            jumps += 1
        elif diff > 14 and s is None:
            cuts += 1
            shot_start = t + 1
        elif s is not None and t + 3 < T and t - shot_start >= 0:
            s3 = scale(t, t + 3)   # 1 detik: zoom pelan baru terlihat setelah beberapa frame
            if s3 is not None:
                drift.append(math.log(s3))
    minutes = max(1e-6, (T - 1) / fps / 60)
    out["jumps_per_min"] = round(jumps / minutes, 1)
    out["cuts_per_min"] = round(cuts / minutes, 1)
    if len(drift) >= 6:
        d = np.abs(np.array(drift))
        out["slow_zoom"] = bool(np.median(d) > 0.012 and float(np.mean(d > 0.008)) > 0.6)
    out["measured"] = readable >= 0.5 * (T - 1)
    return out
