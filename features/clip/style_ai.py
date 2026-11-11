"""
Nero · Clip Maker - baca & tiru gaya editing dari clip referensi dengan AI lokal gratis (Ollama).

Dua lapis pembacaan:
  1. Pengukuran piksel (engine.analyze_reference_style): ukuran, posisi, jumlah kata, warna, judul,
     progress bar, tata letak, zoom. Angkanya tepat, jadi selalu didahulukan.
  2. AI yang bisa melihat gambar: hal yang sulit diukur, yaitu jenis font (dibandingkan dengan lembar
     contoh font Nero), cara menyorot kata (warna / kotak / karaoke), garis tepi, bayangan, kotak gelap,
     gaya judul, nuansa warna video, plus nama & ringkasan gaya. AI juga menjadi cadangan bila
     pengukuran tidak menemukan subtitle (mis. subtitle tanpa garis tepi).
Tanpa AI lokal, hasil pengukuran saja tetap dipakai.
"""
from __future__ import annotations

import os
import re
import subprocess

import numpy as np

import local_ai

from . import engine as core

# urutan baris di lembar contoh font (nomor = posisi + 1); hanya font yang ada di komputer ini yang ikut
FONT_ORDER = ["impact", "anton", "bebas", "montserrat", "poppins", "arial", "segoe", "bahnschrift",
              "verdana", "georgia", "comic"]
COLORS_EN = {"white": "putih", "yellow": "kuning", "green": "hijau", "red": "merah", "blue": "biru",
             "pink": "pink", "orange": "oranye", "purple": "ungu", "teal": "toska"}
COLORS_ID = {v: k for k, v in COLORS_EN.items()}
HIGHLIGHT = {"color": "warna", "box": "kotak", "karaoke": "karaoke", "none": "tanpa"}
OUTLINE = {"none": 0, "thin": 1, "normal": 2, "thick": 3}
TITLES = {"white_box": "putih", "yellow_box": "kuning", "black_box": "hitam", "red_box": "merah",
          "text_only": "tanpa"}
LAYOUTS = {"face_crop": "face", "two_people_split": "split", "full_video_blurred_background": "blur",
           "full_video_black_background": "hitam", "center_crop": "center", "original_vertical": "center"}
LOOKS = {"natural": "asli", "vivid": "cerah", "warm": "hangat", "cool": "dingin", "black_white": "hitamputih",
         "cinematic": "sinematik", "faded": "pudar"}
POSITIONS = {"top": 0.3, "upper_middle": 0.42, "middle": 0.5, "lower_middle": 0.62, "bottom": 0.75}

# Petunjuk untuk model ditulis dalam bahasa Inggris: model kecil (2-8B) jauh lebih patuh dengan
# instruksi berbahasa Inggris. Nama & ringkasan tetap diminta dalam bahasa Indonesia.
SYSTEM = ("You are an expert short-form video editor (TikTok, Instagram Reels, YouTube Shorts). You look at frames "
          "of a vertical video and describe its editing style precisely. Describe only what you actually see. "
          "Answer with JSON only.")


def available_fonts() -> list[str]:
    out = []
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts") if os.name == "nt" else None
    for key in FONT_ORDER:
        file = core.CAPTION_FONTS[key][0]
        if os.path.isfile(os.path.join(core.FONTS_DIR, file)) or (win and os.path.isfile(os.path.join(win, file))):
            out.append(key)
    return out


def schema(n_fonts: int) -> dict:
    s = lambda *vals: {"type": "string", "enum": list(vals)}  # noqa: E731
    props = {
        "has_subtitles": {"type": "boolean"},
        # tanpa pilihan "tidak ada": model kecil cenderung memilih jalan keluar itu daripada membandingkan
        "font_number": s(*[str(i) for i in range(1, n_fonts + 1)]),
        "uppercase": {"type": "boolean"},
        "words_per_screen": s("1", "2", "3", "4"),
        "subtitle_position": s(*POSITIONS),
        "text_color": s(*COLORS_EN),
        "highlight_style": s(*HIGHLIGHT),
        "highlight_color": s(*COLORS_EN, "none"),
        "outline": s(*OUTLINE),
        "shadow": {"type": "boolean"},
        "dark_box": {"type": "boolean"},
        "title_style": s("none", *TITLES),
        "layout": s(*LAYOUTS),
        "color_look": s(*LOOKS),
        "emoji": {"type": "boolean"},
        "name": {"type": "string"},
        "summary": {"type": "string"},
    }
    return {"type": "object", "properties": props, "required": list(props)}


# --------------------------------------------------------------------------
# Gambar untuk AI
# --------------------------------------------------------------------------
def _grab_jpeg(path: str, t: float, vf: str) -> bytes | None:
    r = subprocess.run([core.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
                        "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **core._popen_kwargs())
    return r.stdout if r.returncode == 0 and len(r.stdout) > 500 else None


def pick_times(measure: dict, seconds: float, n: int = 3) -> list[float]:
    """Waktu frame yang dikirim ke AI: tersebar, diutamakan saat subtitle terlihat."""
    want = [seconds * k for k in (0.2, 0.5, 0.8)][:n]
    cap = measure.get("caption_times") or []
    if cap:
        want = [min(cap, key=lambda c: abs(c - w)) for w in want]
    return sorted(dict.fromkeys(round(max(0.3, w), 2) for w in want))


def frame_images(path: str, times: list[float]) -> list[bytes]:
    return [j for t in times if (j := _grab_jpeg(path, t, "scale=432:-2"))]


def contact_sheet(frames: list[bytes]) -> bytes | None:
    """Beberapa frame berdampingan dalam satu gambar. Ollama memperbesar/memperkecil SETIAP gambar ke
    ±1.000 token apa pun ukurannya, jadi satu gambar gabungan jauh lebih hemat konteks daripada tiga."""
    import cv2
    imgs = [im for j in frames if (im := cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_COLOR)) is not None]
    if not imgs:
        return None
    h = min(im.shape[0] for im in imgs)
    cols = []
    for im in imgs:
        cols += [cv2.resize(im, (int(im.shape[1] * h / im.shape[0]), h)), np.full((h, 12, 3), 255, np.uint8)]
    ok, buf = cv2.imencode(".jpg", np.hstack(cols[:-1]), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buf.tobytes() if ok else None


def caption_strip(path: str, band, times: list[float]) -> bytes | None:
    """Potongan area subtitle dari beberapa saat, ditumpuk ke bawah, supaya hurufnya terlihat jelas."""
    import cv2
    if not band:
        return None
    a, b = max(0.0, band[0] - 0.025), min(1.0, band[1] + 0.025)
    crops = []
    for t in times:
        j = _grab_jpeg(path, t, f"crop=iw:ih*{b - a:.4f}:0:ih*{a:.4f},scale=896:-2")
        if j:
            img = cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                crops.append(img)
    if not crops:
        return None
    w = crops[0].shape[1]
    sep = np.full((10, w, 3), 128, np.uint8)
    rows = []
    for c in crops:
        rows += [cv2.resize(c, (w, int(c.shape[0] * w / c.shape[1]))), sep]
    ok, buf = cv2.imencode(".jpg", np.vstack(rows[:-1]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes() if ok else None


_sheet_cache: dict[tuple, bytes] = {}
SHEET_TEXT = "Kata subtitle 2026"   # tulisan contoh di lembar font


def clean_name(v) -> str:
    """Nama gaya dari AI. Model kecil kadang menyalin tulisan di gambar (mis. contoh di lembar font): buang."""
    name = re.sub(r"\s+", " ", str(v or "")).strip(" .\"'")[:40]
    sheet = set(SHEET_TEXT.lower().split())
    return "" if not name or set(name.lower().split()) & sheet else name


_HL_WORD = {"kotak": "Kotak", "karaoke": "Karaoke", "tanpa": "Polos", "warna": "Sorot"}


def style_name(ai_name: str, style: dict) -> str:
    """Nama untuk Gaya saya. Nama dari AI dipakai bila memang menggambarkan tampilan (menyebut warna);
    model kecil kadang memberi nama acak, maka dibuat nama dari gayanya, mis. "Kotak Ungu Montserrat"."""
    colors = set(core.CAPTION_COLORS) | {"hitam", "emas", "neon"}
    if ai_name and set(ai_name.lower().split()) & colors:
        return ai_name
    if not style.get("captions", True):
        return ai_name
    hl = style.get("caption_highlight", "warna")
    color = style.get("caption_base" if hl == "tanpa" else "caption_color", "kuning")
    font = next((label for key, label in _FONT_LABEL.items() if key == style.get("caption_font")), "")
    return " ".join(x for x in (_HL_WORD.get(hl, "Sorot"), color.capitalize(), font) if x)


_FONT_LABEL = {"impact": "Impact", "anton": "Anton", "bebas": "Bebas", "montserrat": "Montserrat",
               "poppins": "Poppins", "arial": "Arial Black", "segoe": "Segoe", "bahnschrift": "Bahnschrift",
               "verdana": "Verdana", "georgia": "Georgia", "comic": "Comic"}


def clean_summary(v) -> str:
    """Ringkasan dari AI: paling banyak dua kalimat berbeda (model kecil suka mengulang kalimat)."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", str(v or "").strip()):
        if s and s.lower() not in (x.lower() for x in out):
            out.append(s)
        if len(out) == 2:
            break
    return " ".join(out)[:400]


def font_sheet(fonts: list[str], upper: bool | None) -> bytes:
    """Lembar contoh font bernomor. Membandingkan jauh lebih mudah bagi AI kecil daripada menebak nama font."""
    import cv2
    from PIL import Image, ImageDraw
    key = (tuple(fonts), upper)
    if key in _sheet_cache:
        return _sheet_cache[key]
    text = SHEET_TEXT.upper() if upper is not False else SHEET_TEXT
    # Ollama mengubah setiap gambar ke ±1.000 token apa pun ukurannya; ukuran ini cukup jelas & cepat dibuat
    row_h, W = 80, 768
    img = Image.new("RGB", (W, row_h * len(fonts)), (92, 92, 92))
    d = ImageDraw.Draw(img)
    label = core._load_font(32)
    for i, k in enumerate(fonts):
        y = i * row_h
        if i:
            d.line((0, y, W, y), fill=(140, 140, 140), width=2)
        d.rectangle((0, y, 60, y + row_h), fill=(20, 20, 20))
        d.text((30, y + row_h / 2), str(i + 1), font=label, fill=(255, 255, 255), anchor="mm")
        f = core._font_by_key(k, 54)
        d.text((78, y + row_h / 2), text, font=f, fill=(255, 255, 255), anchor="lm",
               stroke_width=4, stroke_fill=(0, 0, 0))
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    _sheet_cache[key] = buf.tobytes()
    return _sheet_cache[key]


# --------------------------------------------------------------------------
# Pertanyaan untuk AI
# --------------------------------------------------------------------------
_LAYOUT_EN = {"face": "the original wide video is cropped to follow the speaker's face",
              "split": "two people stacked (top half / bottom half)",
              "blur": "the full wide video in the middle with a blurred background above and below",
              "hitam": "the full wide video in the middle with black bars above and below",
              "center": "a centered crop, or the original video was already vertical"}


def facts(style: dict, measure: dict) -> str:
    """Hasil pengukuran piksel dalam kalimat, supaya AI tidak menebak ulang hal yang sudah pasti."""
    out = []
    if style.get("captions"):
        words = style.get("caption_words")
        case = {True: "UPPERCASE", False: "normal case"}.get(style.get("caption_upper"), "case unclear")
        out.append(f"- Spoken-word subtitles found around {round(style.get('caption_pos', 0.68) * 100)}% from the "
                   f"top, at most {words} word(s) at a time, {case}.")
        if style.get("caption_base") == style.get("caption_color"):
            out.append(f"- Subtitle letters are mostly {COLORS_ID.get(style.get('caption_base'), 'white')}.")
        else:
            out.append(f"- Subtitle text is mostly {COLORS_ID.get(style.get('caption_base'), 'white')}; "
                       f"{COLORS_ID.get(style.get('caption_color'), 'yellow')} is used for emphasis.")
    else:
        out.append("- The pixel scan did NOT find outlined subtitles (they may be missing, or have no outline).")
    if style.get("title_on"):
        secs = style.get("title_secs")
        out.append("- A fixed headline is shown near the top " + ("for the whole video." if not secs else
                                                                    f"for the first {secs} seconds."))
    else:
        out.append("- No fixed headline was found at the top.")
    if style.get("layout"):
        out.append(f"- Layout: {_LAYOUT_EN[style['layout']]}.")
    out.append(f"- Progress bar: {'yes' if style.get('progress_bar') else 'no'}.")
    m = measure.get("motion") or {}
    if m:
        out.append(f"- Camera: {m.get('jumps_per_min', 0)} sudden zoom jumps and {m.get('cuts_per_min', 0)} scene "
                   "cuts per minute.")
    return "\n".join(out)


def prompt(style: dict, measure: dict, n_frames: int, has_strip: bool, n_fonts: int) -> str:
    imgs = [f"- Image 1: {n_frames} full frames from the video side by side (separated by white bars), "
            "taken at different moments from left to right." if n_frames > 1 else
            "- Image 1: a full frame from the video."]
    k = 2
    if has_strip:
        imgs.append(f"- Image {k}: close-up strips of the subtitle area from several moments (stacked).")
        k += 1
    imgs.append(f"- Image {k}: a font sample sheet with {n_fonts} numbered rows. Every row writes the same words "
                "in a different font.")
    return f"""Analyze the editing style of this vertical short video so it can be copied.

{chr(10).join(imgs)}

Measurements already made by pixel analysis (trust them):
{facts(style, measure)}

Fill every field:
- has_subtitles: true if there are captions of the spoken words that change as the person talks. A headline that stays the same is NOT a subtitle.
- font_number: the row of the font sheet whose letters look MOST like the subtitle letters. Look at the subtitle close-up, then at each row of the font sheet, and compare letter width (narrow/condensed vs wide), stroke thickness, roundness and serifs. Always pick the closest row.
- uppercase: true if subtitles are written in CAPITAL letters.
- words_per_screen: the largest number of subtitle words usually visible at once.
- subtitle_position: where the subtitles sit vertically.
- text_color: the color of most subtitle letters.
- highlight_style: how the currently spoken word is emphasized. "color" = one word has a different letter color; "box" = one word has a solid colored rectangle behind it; "karaoke" = the words already spoken are colored from left to right; "none" = all words look the same.
- highlight_color: the color of that emphasized word or box ("none" if highlight_style is "none").
- outline: thickness of the dark outline around subtitle letters.
- shadow: true if the letters have a drop shadow.
- dark_box: true if the whole subtitle sits on a dark semi-transparent rectangle.
- title_style: the fixed headline near the top: its box color, "text_only" if it has no box, "none" if there is no headline.
- layout: how the footage fills the vertical frame.
- color_look: the overall color grading of the footage (not the text).
- emoji: true if emoji or stickers appear next to the subtitles.
- name: a short catchy name for this style in Indonesian, 2-4 words, describing its look (for example "Podcast Kuning Tegas" or "Kotak Ungu Santai"). Do not copy any text written in the images.
- summary: 1-2 short sentences in Indonesian that explain this editing style to a beginner. Describe the look, not what the people say."""


# --------------------------------------------------------------------------
# Gabungkan pengukuran + AI
# --------------------------------------------------------------------------
def _look_ok(look: str, color: dict) -> bool:
    """Nuansa warna dari AI hanya dipakai bila angka warnanya mendukung (AI kecil sering menebak)."""
    sat, warm, bright = color.get("sat", 60), color.get("warm", 0), color.get("bright", 120)
    # kulit & lampu ruangan memang hangat, jadi "hangat" baru dipercaya bila jelas sekali
    return {"asli": True, "cerah": sat >= 95, "hangat": warm >= 26, "dingin": warm <= -2,
            "hitamputih": sat < 28, "sinematik": sat < 120, "pudar": sat < 80 and bright > 70}.get(look, False)


def merge(measured: dict, ai: dict | None, measure: dict, fonts: list[str]) -> tuple[dict, dict]:
    """Hasil: (gaya, sumber per kunci: 'ukur' = pengukuran piksel, 'ai' = penilaian AI)."""
    style = dict(measured)
    src = {k: "ukur" for k in style}
    if not ai:
        return style, src

    def put(k, v):
        if v is not None:
            style[k], src[k] = v, "ai"

    try:
        n = int(ai.get("font_number") or 0)
    except (TypeError, ValueError):
        n = 0
    font = fonts[n - 1] if 1 <= n <= len(fonts) else None
    hl = HIGHLIGHT.get(ai.get("highlight_style"))
    hl_color = COLORS_EN.get(ai.get("highlight_color"))

    def caption_look():
        put("caption_font", font)
        if "caption_highlight" not in measured:   # kotak sorot terukur dari piksel lebih pasti daripada AI
            put("caption_highlight", hl)
        put("caption_stroke", OUTLINE.get(ai.get("outline")))
        put("caption_shadow", bool(ai.get("shadow")))
        put("caption_box", bool(ai.get("dark_box")))

    if measured.get("captions"):
        caption_look()
        # pengukuran hanya menemukan huruf terang yang menempel piksel gelap: pasti ada garis tepi,
        # bayangan, atau kotak gelap. Bila AI bilang tidak ada semuanya, anggap garis tepi tipis.
        if style.get("caption_stroke") == 0 and not style.get("caption_shadow") and not style.get("caption_box"):
            put("caption_stroke", 1)
        if "caption_upper" not in style:
            put("caption_upper", bool(ai.get("uppercase")))
        # kotak sorot sering tidak terbaca sebagai warna huruf oleh pengukuran
        if hl in ("kotak", "karaoke") and hl_color and style.get("caption_color") == style.get("caption_base"):
            put("caption_color", hl_color)
    elif ai.get("has_subtitles"):
        # pengukuran tidak menemukan subtitle (mis. tanpa garis tepi): pakai pembacaan AI seluruhnya
        put("captions", True)
        caption_look()
        put("caption_upper", bool(ai.get("uppercase")))
        put("caption_pos", POSITIONS.get(ai.get("subtitle_position")))
        try:
            put("caption_words", max(1, min(4, int(ai.get("words_per_screen") or 3))))
        except (TypeError, ValueError):
            pass
        put("caption_base", COLORS_EN.get(ai.get("text_color")))
        put("caption_color", hl_color or COLORS_EN.get(ai.get("text_color")))

    title = ai.get("title_style")
    if style.get("title_on") and "title_bg" not in style and title in TITLES:
        put("title_bg", TITLES[title])

    look = LOOKS.get(ai.get("color_look"))
    if "filter" not in style and look and _look_ok(look, measure.get("color") or {}):
        put("filter", look)
    layout = LAYOUTS.get(ai.get("layout"))
    # "potong tengah" adalah tebakan cadangan pengukuran (mis. latar blur tidak terbaca karena zoom,
    # atau wajah tidak terdeteksi di video gelap), jadi penilaian AI boleh menggantinya
    if "layout" not in style or (style["layout"] == "center" and layout in ("blur", "hitam", "face")):
        put("layout", layout)
    return style, src


def analyze(path: str, *, ai_url: str | None, ai_model: str | None, use_ai: bool = True,
            stage=lambda label, x: None, alive=lambda: None) -> dict:
    """Baca gaya clip referensi. Hasil: {style, sources, notes, seconds, ai: {model, name, summary} | None}."""
    stage("Mengukur subtitle, judul, tata letak & zoom...", 0.3)
    res = core.analyze_reference_style(path)
    alive()
    style, notes, measure = res["style"], list(res["notes"]), res.get("measure") or {}
    out = {"style": style, "sources": {k: "ukur" for k in style}, "notes": notes, "seconds": res["seconds"],
           "ai": None}
    if not use_ai:
        notes.append("Dibaca tanpa AI: jenis font & cara menyorot kata tidak ditiru.")
        return out

    st = local_ai.status(ai_url)
    model = local_ai.pick_model(st, ai_model) if st["ok"] else None
    if not st["ok"] or not model:
        why = st["error"] if not st["ok"] else "Belum ada model AI yang bisa melihat gambar di Ollama."
        notes.append(f"{why} Gaya dibaca tanpa AI: jenis font & cara menyorot kata tidak ditiru.")
        out["ai_missing"] = True
        return out

    stage("Menyiapkan frame untuk AI...", 0.45)
    times = pick_times(measure, res["seconds"])
    frames = frame_images(path, times)
    together = contact_sheet(frames)
    strip = caption_strip(path, measure.get("caption_band"), times) if style.get("captions") else None
    fonts = available_fonts()
    sheet = font_sheet(fonts, style.get("caption_upper"))
    images = ([together] if together else []) + ([strip] if strip else []) + [sheet]
    alive()

    label = f"AI lokal ({model}) sedang melihat clip... Pertama kali bisa 1-3 menit."
    stage(label, 0.55)
    try:
        ai = local_ai.chat_json(prompt(style, measure, len(frames), bool(strip), len(fonts)), schema(len(fonts)),
                                images, url=ai_url, model=model, system=SYSTEM, alive=alive,
                                on_token=lambda n: stage(label, min(0.95, 0.55 + n / 900)))
    except local_ai.LocalAIError as e:
        notes.append(f"{e} Gaya dibaca tanpa AI.")
        return out
    alive()
    merged, sources = merge(style, ai, measure, fonts)
    out.update(style=merged, sources=sources,
               ai={"model": model, "name": clean_name(ai.get("name")), "summary": clean_summary(ai.get("summary"))})
    if ai.get("emoji"):
        notes.append("AI melihat emoji/stiker di samping subtitle; Nero belum bisa menambahkannya.")
    if ai.get("has_subtitles") and not merged.get("captions"):
        notes.append("AI melihat subtitle tetapi tidak bisa diukur; periksa pratinjau.")
    return out
