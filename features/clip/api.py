"""
Nero · Clip Maker - API, antrian, dan pekerja fitur pembuat clip pendek.

Semua rute di sini ada di bawah /api/clip (didaftarkan oleh app.py).
Proyek disimpan di data/clip/projects, hasil render di output/clip.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import threading
import time
import traceback
import uuid

from flask import Blueprint, Response, jsonify, request, send_from_directory, abort

import common
from common import dir_size_mb, remove_files, remove_later, safe_name

from . import engine as core
from . import style_ai
from .presets import DEFAULT_STYLE, PRESET_BY_ID, PRESETS, apply_look, look_of

ID = "clip"
DATA = common.data_dir(ID)
PROJ = os.path.join(DATA, "projects")
OUTPUT = common.output_dir(ID)
STYLES_PATH = os.path.join(DATA, "styles.json")   # pustaka "Gaya saya"
THUMBS = os.path.join(DATA, "thumbs")             # gambar contoh tiap gaya (bisa dibuat ulang)
os.makedirs(PROJ, exist_ok=True)

# Bagian "clip" di data/settings.json. API key, model AI, dan cookies browser ada di pengaturan umum Nero.
SETTINGS = {
    "whisper_model": "small",
    "language": "id",
    "n_clips": 5,
    "min_len": 20,
    "max_len": 60,
    "auto_render": False,
    "style": dict(DEFAULT_STYLE),
    # gaya pustaka / preset yang terakhir dipakai sebagai gaya aktif ("" = diatur sendiri)
    "active_style_id": "",
}
LANGUAGES = {"id", "en", "auto", "ms", "jv"}

bp = Blueprint(ID, __name__)
lock = threading.RLock()
# Dua antrian terpisah: video panjang yang sedang ditranskrip tidak menahan render clip lain.
analyze_q: "queue.Queue[tuple]" = queue.Queue()
render_q: "queue.Queue[tuple]" = queue.Queue()
projects: dict[str, dict] = {}

class Cancelled(Exception):
    """Tugas dibatalkan pengguna atau proyeknya dihapus."""


def check_job(pid, obj, token):
    """Setiap tugas membawa token; bila token di proyek/clip berganti, tugas lama berhenti."""
    if pid not in projects or obj.get("job") != token:
        raise Cancelled()


# --------------------------------------------------------------------------
def load_settings():
    """Pengaturan umum (API key, model AI, cookies) + pengaturan clip dalam satu kamus."""
    return common.feature_settings(ID)


def pdir(pid):
    return os.path.join(PROJ, pid)


def save_project(p):
    with lock:
        if p["id"] not in projects:  # sudah dihapus: jangan tulis ulang project.json
            return
        light = {k: v for k, v in p.items() if k not in ("segments", "job")}
        with open(os.path.join(pdir(p["id"]), "project.json"), "w", encoding="utf-8") as f:
            json.dump(light, f, ensure_ascii=False, indent=1)


def load_projects():
    for pid in os.listdir(PROJ):
        fp = os.path.join(PROJ, pid, "project.json")
        if not os.path.exists(fp):
            # sisa proyek yang dihapus tapi filenya sempat terkunci
            shutil.rmtree(pdir(pid), ignore_errors=True)
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                p = json.load(f)
            if p.get("status") not in ("siap", "gagal"):
                if p.get("clips"):  # pencarian ulang terhenti: daftar clip lama masih utuh
                    p["status"], p["stage"] = "siap", "Pencarian ulang terhenti (aplikasi ditutup)."
                else:
                    p["status"], p["stage"] = "gagal", "Terhenti (aplikasi ditutup). Klik Ulangi."
            for c in p.get("clips", []):
                c.pop("job", None)
                if c.get("render_status") in ("antri", "proses"):
                    c["render_status"] = None
            projects[pid] = p
        except Exception:
            pass


def segments_of(p):
    fp = os.path.join(pdir(p["id"]), "transcript.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    return []


def all_words(segs):
    return [w for s in segs for w in s["words"]]


def set_stage(p, stage, prog=None, status=None):
    with lock:
        p["stage"] = stage
        if prog is not None:
            p["progress"] = round(prog, 3)
        if status:
            p["status"] = status


def busy(p):
    return p.get("status") in ("antri", "proses") or any(
        c.get("render_status") in ("antri", "proses") for c in p.get("clips", []))


# --------------------------------------------------------------------------
# Pekerja: satu untuk analisis, satu untuk render
# --------------------------------------------------------------------------
def do_analyze(pid, token):
    p = projects[pid]
    if p.get("job") != token:
        return
    s = load_settings()
    d = pdir(pid)
    lang = p.get("language") or s["language"]
    wav = os.path.join(d, "audio.wav")
    tr = os.path.join(d, "transcript.json")

    def alive():
        check_job(pid, p, token)

    def stage_cb(label):
        def cb(x):
            alive()
            set_stage(p, label, x)
        return cb

    try:
        p["error"], p["warning"] = "", ""
        # 1. sumber
        src = p.get("source")
        if not src or not os.path.exists(os.path.join(d, src)):
            if not p.get("url"):
                raise RuntimeError("Video sumber sudah dihapus dan tidak ada link untuk mengunduh ulang.")
            set_stage(p, "Mengunduh video...", 0, "proses")
            info = core.download_video(p["url"], d, progress=stage_cb("Mengunduh video..."),
                                       cookies_browser=s.get("cookies_browser") or None)
            alive()
            p["source"] = os.path.basename(info["path"])
            p["title"] = info["title"]
            p.pop("source_removed", None)
            save_project(p)
        src_path = os.path.join(d, p["source"])
        vi = core.probe(src_path)
        p["duration"], p["width"], p["height"] = vi.duration, vi.width, vi.height

        # 2. audio + transkrip
        if not os.path.exists(tr):
            alive()
            set_stage(p, "Menyiapkan audio...", 0, "proses")
            core.extract_audio(src_path, wav)
            alive()
            dev = "GPU" if core.transcribe_device() == "cuda" else "CPU"
            set_stage(p, f"Membuat transkrip ({dev}, model {s['whisper_model']})...", 0)
            segs = core.transcribe(wav, s["whisper_model"], lang,
                                   progress=stage_cb(f"Membuat transkrip ({dev})..."))
            alive()
            with open(tr, "w", encoding="utf-8") as f:
                json.dump(segs, f, ensure_ascii=False)
        segs = segments_of(p)

        # 3. momen terbaik (timeline/link/instruksi dari kolom referensi lebih dulu)
        alive()
        set_stage(p, "Mencari momen paling menarik...", 0.5, "proses")
        clips, used_ai, warns = pick_clips(p, segs, s, lang, src_path, wav, alive)
        if warns:
            p["warning"] = " · ".join(warns)[:900]
        alive()
        for c in clips:
            c["id"] = uuid.uuid4().hex[:8]
            c["selected"] = True
            c["render_status"] = None
            c["file"] = None
        with lock:
            alive()
            p["clips"] = clips
            p["used_ai"] = used_ai
            set_stage(p, f"Selesai: {len(clips)} momen ditemukan", 1, "siap")
        save_project(p)
        if p.get("auto_render"):
            for c in clips:
                queue_render(pid, c["id"])
    except Cancelled:
        return
    except Exception as e:
        if pid not in projects or p.get("job") != token:  # dihapus/dibatalkan, bukan kegagalan
            return
        traceback.print_exc()
        msg = str(e)
        if "Sign in to confirm" in msg or re.search(r"\bbot\b", msg, re.I):
            msg += " | Tips: isi 'Ambil cookies dari browser' di Pengaturan Nero (mis. chrome/edge/firefox)."
        p["error"] = msg[:600]
        set_stage(p, "Gagal", None, "gagal")
        save_project(p)
    finally:
        # hemat disk: audio.wav (~2 MB per menit) selalu bisa dibuat ulang dari video
        remove_files(wav)


MAX_REFS = 5  # link clip referensi per proyek


def youtube_id(url):
    m = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/live/|/embed/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def url_time(url):
    """Detik dari ?t= / &start= di link YouTube (t=754, t=754s, t=12m34s, t=1h2m3s)."""
    m = re.search(r"[?&#](?:t|start)=([\dhms.]+)", url or "")
    if not m:
        return None
    v = m.group(1)
    if re.fullmatch(r"\d+(?:\.\d+)?s?", v):
        return float(v.rstrip("s"))
    parts = {u: re.search(rf"(\d+){u}", v) for u in "hms"}
    secs = sum(int(x.group(1)) * k for u, k in (("h", 3600), ("m", 60), ("s", 1)) if (x := parts[u]))
    return float(secs) if any(parts.values()) else None


def load_references(p, links, s, lang, alive):
    """Unduh audio clip referensi lalu buat transkripnya. Hasil disimpan di folder refs/ proyek,
    jadi 'Cari ulang momen' tidak perlu mengunduh lagi."""
    d = os.path.join(pdir(p["id"]), "refs")
    os.makedirs(d, exist_ok=True)
    refs, warns = [], []
    for i, url in enumerate(links, 1):
        cache = os.path.join(d, hashlib.sha1(url.encode("utf-8")).hexdigest()[:12] + ".json")
        if os.path.exists(cache):
            try:
                with open(cache, encoding="utf-8") as f:
                    refs.append(json.load(f))
                continue
            except Exception:
                pass
        tmp = os.path.join(d, "tmp")
        label = f"clip referensi {i}/{len(links)}"
        try:
            alive()
            set_stage(p, f"Mengunduh {label}...", 0)
            info = core.download_reference(url, tmp, s.get("cookies_browser") or None)
            alive()
            wav = os.path.join(tmp, "ref.wav")
            core.extract_audio(info["path"], wav)

            def cb(x):
                alive()
                set_stage(p, f"Membuat transkrip {label}...", x)

            segs = core.transcribe(wav, s["whisper_model"], lang, progress=cb)
            ref = {"url": url, "title": info["title"], "segments": segs}
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(ref, f, ensure_ascii=False)
            refs.append(ref)
        except Cancelled:
            raise
        except Exception as e:
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
            warns.append(f"Clip referensi {i} gagal diproses ({msg[:140]})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return refs, warns


def pick_clips(p, segs, s, lang, src_path, wav, alive):
    """Pilih momen. Isi kolom 'Referensi & instruksi' didahulukan:
    timeline & link referensi yang cocok -> pasti jadi clip; titik waktu -> momen di sekitarnya;
    instruksi/contoh -> mengarahkan AI (atau kata kunci di mode lokal). Sisa jumlah clip diisi otomatis.
    Hasil: (clips, used_ai, peringatan)."""
    warns = []
    brief = core.parse_brief(p.get("brief") or "")
    dur = p.get("duration") or (segs[-1]["end"] if segs else 0)
    n, mn, mx = int(p.get("n_clips") or s["n_clips"]), int(s["min_len"]), int(s["max_len"])
    fixed, points, examples = [], [], []

    for r in brief["ranges"]:
        a, b = r["start"], min(r["end"], dur)
        if a >= dur or b - a < 1:
            why = "melewati durasi video" if a >= dur else "waktu selesai harus setelah waktu mulai"
            warns.append(f"Timeline {core._fmt(r['start'])} - {core._fmt(r['end'])} dilewati: {why}")
            continue
        a, b = core.snap_range(segs, a, b)
        fixed.append({"start": a, "end": b, "note": r["note"], "ref": "timeline"})
    for pt in brief["points"]:
        if pt["t"] < dur:
            points.append(pt)
        else:
            warns.append(f"Titik {core._fmt(pt['t'])} dilewati: melewati durasi video")

    main_id, others = youtube_id(p.get("url")), []
    for url in brief["links"]:
        if main_id and youtube_id(url) == main_id:  # link video ini sendiri, mis. disalin dengan ?t=
            t = url_time(url)
            if t is not None and t < dur:
                points.append({"t": t, "note": ""})
            continue
        if url != p.get("url"):
            others.append(url)
    if len(others) > MAX_REFS:
        warns.append(f"Hanya {MAX_REFS} link referensi pertama yang dipakai.")
        others = others[:MAX_REFS]
    if others:
        refs, w = load_references(p, others, s, lang, alive)
        warns += w
        for ref in refs:
            m = core.match_reference(segs, ref["segments"])
            if m:
                a, b = core.snap_range(segs, m["start"], m["end"], tol=1.5)
                fixed.append({"start": a, "end": b, "note": "", "ref": "link", "ratio": m["ratio"]})
                continue
            text = " ".join(x["text"] for x in ref["segments"]).strip()
            if text:
                examples.append(text[:1500])
            warns.append(f'Clip referensi "{str(ref.get("title", ""))[:60]}" tidak ditemukan di video ini; '
                         "dipakai sebagai contoh gaya/topik.")

    # timeline & link yang menunjuk momen yang sama cukup dibuat sekali
    uniq = []
    for f in fixed:
        if not any(min(f["end"], u["end"]) - max(f["start"], u["start"])
                   > 0.5 * min(f["end"] - f["start"], u["end"] - u["start"]) for u in uniq):
            uniq.append(f)
    fixed = uniq

    energy_cache = []

    def energy():
        if not energy_cache:
            if not os.path.exists(wav):
                core.extract_audio(src_path, wav)
            energy_cache.append(core.audio_energy(wav))
        return energy_cache[0]

    clips, used_ai = None, False
    if s.get("api_key"):
        set_stage(p, "Claude sedang memilih momen terbaik...", 0.5)
        try:
            clips, note = core.find_highlights_ai(
                segs, s["api_key"], max(n - len(fixed), len(points)), mn, mx, s["ai_model"], p.get("title", ""),
                brief={"instructions": brief["instructions"], "examples": examples, "fixed": fixed, "points": points})
            used_ai = bool(clips)
            if note:
                warns.append(note)
        except Exception as e:
            clips = None
            warns.append(f"AI gagal, memakai deteksi lokal. ({e})"[:300])
    alive()
    if clips:
        missing = [pt for pt in points if not any(c["start"] - 1 <= pt["t"] <= c["end"] for c in clips)]
        if missing:  # AI melewatkan titik riset: tambahkan momen di sekitarnya
            clips += core.find_highlights_heuristic(segs, energy(), 0, mn, mx, points=missing,
                                                    taken=[(c["start"], c["end"]) for c in clips])
    else:
        want, avoid = core.brief_keywords(brief["instructions"])
        if examples:  # tanpa AI: kata yang sering muncul di clip referensi jadi petunjuk topik
            want += [h[1:] for h in core._hashtags(" ".join(examples), 5) if h not in ("#fyp", "#viral")]
        clips = core.find_highlights_heuristic(segs, energy(), max(0, n - len(fixed) - len(points)), mn, mx,
                                               keywords=want, avoid=avoid, points=points, fixed=fixed)
    clips.sort(key=lambda c: c["start"])
    return clips, used_ai, warns


def output_files(rel):
    base = os.path.join(OUTPUT, rel).rsplit(".", 1)[0]
    return [base + ext for ext in (".mp4", ".srt", ".jpg", "_caption.txt")]


def do_render(pid, cid, token):
    p = projects[pid]
    c = next((x for x in p.get("clips", []) if x["id"] == cid), None)
    if not c or c.get("job") != token:
        return
    if not p.get("source"):
        c["render_status"], c["error"] = "gagal", "Video sumber sudah dihapus."
        save_project(p)
        return
    style = project_style(p, load_settings())
    out = None
    try:
        c["render_status"], c["render_progress"], c["error"] = "proses", 0, ""
        segs = segments_of(p)
        words = [w for w in all_words(segs) if w["end"] > c["start"] and w["start"] < c["end"]]
        # nama stabil: memakai id clip, bukan nomor urut yang bisa bergeser
        name = f"{safe_name(p.get('title', 'video'), 30)}_{safe_name(c.get('title', ''), 30)}_{c['id'][:4]}"
        out_dir = os.path.join(OUTPUT, safe_name(p.get("title", pid), 50))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, name + ".mp4")

        def prog(x):
            check_job(pid, c, token)  # hentikan render bila dibatalkan / proyek dihapus
            c["render_progress"] = round(x, 3)

        core.render_clip(os.path.join(pdir(pid), p["source"]), c["start"], c["end"], out, words,
                         style, c.get("title", "") if style.get("title_on", True) else "", progress=prog)
        # waktu subtitle .srt mengikuti video hasil (bisa lebih pendek bila jeda dibuang)
        keep, rel = core.clip_timeline(words, c["start"], c["end"], style)
        core.write_srt(rel, 0, sum(m - k for k, m in keep) / core.OUT_FPS, out.rsplit(".", 1)[0] + ".srt")
        with open(out.rsplit(".", 1)[0] + "_caption.txt", "w", encoding="utf-8") as f:
            f.write((c.get("caption") or c.get("title", "")) + "\n\n" + " ".join(c.get("hashtags", [])))
        rel = os.path.relpath(out, OUTPUT).replace("\\", "/")
        old = c.get("file")
        if old and old != rel:  # judul berubah: buang hasil render lama clip ini
            remove_later(remove_files(*output_files(old)))
        c["file"] = rel
        c.pop("subs_changed", None)
        c["rendered_at"] = int(time.time())  # untuk memuat ulang thumbnail di halaman
        c["render_status"], c["render_progress"] = "selesai", 1
    except Exception as e:
        if out:  # buang file sementara dari render yang tidak selesai
            remove_files(out + ".tmp.mp4", out + ".log")
            try:
                os.rmdir(os.path.dirname(out))  # hanya terhapus bila folder kosong
            except OSError:
                pass
        if pid not in projects or c.get("job") != token:
            return
        traceback.print_exc()
        c["render_status"], c["error"] = "gagal", str(e)[:500]
    save_project(p)


def worker(q, kind):
    while True:
        job = q.get()
        pid = job[0]
        try:
            if pid in projects:
                if kind == "analyze":
                    do_analyze(pid, job[1])
                else:
                    do_render(pid, job[1], job[2])
        except Exception:
            traceback.print_exc()  # jangan sampai pekerja mati dan antrian macet
        finally:
            if pid not in projects:
                # proyek dihapus saat diproses: sekarang file sudah tidak terkunci
                shutil.rmtree(pdir(pid), ignore_errors=True)
            q.task_done()


def queue_analyze(pid):
    p = projects[pid]
    with lock:
        p["job"] = uuid.uuid4().hex
        p["status"], p["stage"], p["progress"], p["error"] = "antri", "Menunggu giliran...", 0, ""
    analyze_q.put((pid, p["job"]))


def queue_render(pid, cid):
    p = projects.get(pid)
    if not p or not p.get("source"):
        return False
    with lock:
        c = next((x for x in p.get("clips", []) if x["id"] == cid), None)
        if not c or c.get("render_status") in ("antri", "proses"):
            return False
        c["job"] = uuid.uuid4().hex
        c["render_status"], c["render_progress"], c["error"] = "antri", 0, ""
    render_q.put((pid, cid, c["job"]))
    return True


BRIEF_LIMIT = 20_000  # karakter kolom "Referensi & instruksi"


def clean_brief(v):
    return str(v or "").strip()[:BRIEF_LIMIT]


def new_project(url=None, source=None, title=None, n_clips=None, auto_render=False, language=None, brief=None,
                style_id=None):
    pid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    os.makedirs(pdir(pid), exist_ok=True)
    p = {"id": pid, "url": url, "source": source, "title": title or url or "Video",
         "status": "antri", "stage": "Menunggu giliran...", "progress": 0, "clips": [],
         "created": time.time(), "n_clips": n_clips, "auto_render": auto_render, "error": "",
         "language": language if language in LANGUAGES else None, "brief": clean_brief(brief),
         "style_id": style_id if find_style(style_id) else None}
    projects[pid] = p
    save_project(p)
    return p


# --------------------------------------------------------------------------
# Pustaka gaya: "Gaya saya" (data/clip/styles.json) + preset bawaan
# --------------------------------------------------------------------------
styles_lock = threading.RLock()


def load_styles() -> list[dict]:
    with styles_lock:
        if os.path.exists(STYLES_PATH):
            try:
                with open(STYLES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
            except Exception:
                traceback.print_exc()
        return []


def save_styles(items: list[dict]) -> None:
    with styles_lock:
        tmp = STYLES_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STYLES_PATH)


def find_style(sid) -> dict | None:
    if not sid:
        return None
    if sid in PRESET_BY_ID:
        return PRESET_BY_ID[sid]
    return next((x for x in load_styles() if x["id"] == sid), None)


def project_style(p, s) -> dict:
    """Gaya untuk merender clip proyek ini: gaya pilihan proyek (dari pustaka) atau gaya aktif."""
    cur = {**DEFAULT_STYLE, **s["style"]}
    chosen = find_style(p.get("style_id"))
    if chosen:
        return apply_look(cur, chosen["style"])
    return {**cur, **(p.get("style") or {})}


def clean_style_name(v, fallback="Gaya baru") -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:40] or fallback


def add_style(name, style, **meta) -> dict:
    with styles_lock:
        items = load_styles()
        names = {x["name"] for x in items}
        base, k = clean_style_name(name), 2
        name = base
        while name in names:  # nama kembar diberi nomor
            name = f"{base} {k}"
            k += 1
        entry = {"id": uuid.uuid4().hex[:10], "name": name, "style": look_of(style), "created": int(time.time()),
                 **meta}
        items.insert(0, entry)
        save_styles(items)
    return entry


def _preview_source(pid=None):
    """Proyek, detik, dan clip untuk frame contoh: proyek `pid` atau proyek siap terbaru yang videonya masih ada.
    (None, 0, None) = belum ada video, pakai latar contoh."""
    cands = [projects[pid]] if pid in projects else sorted(projects.values(), key=lambda x: -x.get("created", 0))
    for p in cands:
        if p.get("status") == "siap" and p.get("source") and os.path.exists(os.path.join(pdir(p["id"]), p["source"])):
            clip = (p.get("clips") or [None])[0]
            t = clip["start"] + 1.0 if clip else (p.get("duration") or 10) * 0.3
            return p, t, clip
    return None, 0.0, None


def preview_jpeg(style: dict, pid=None, width=core.OUT_W // 2) -> bytes:
    """Satu frame contoh dengan gaya ini (dipakai pratinjau & gambar kartu gaya)."""
    p, t, clip = _preview_source(pid)
    if p:
        words = [w for w in all_words(segments_of(p)) if t - 0.05 <= w["start"] < t + 4]
        title = (clip or {}).get("title") or p.get("title", "")
        return core.render_preview(os.path.join(pdir(p["id"]), p["source"]), t, words, style, title, width)
    return core.render_preview(None, 0, [], style, "Contoh judul hook yang menarik", width)


def thumb_key(style: dict, src=None) -> str:
    """Kunci gambar contoh: berubah bila gayanya atau video contohnya berubah."""
    p, t, _ = src or _preview_source()
    raw = json.dumps([look_of(style), p["id"] if p else "", round(t, 2), THUMB_W], sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


THUMB_W = 270  # lebar gambar kartu gaya (px)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@bp.get("/state")
def state():
    for _ in range(5):
        try:
            with lock:
                items = sorted(projects.values(), key=lambda p: -p.get("created", 0))
                body = json.dumps({
                    "projects": [{**p, "size_mb": dir_size_mb(pdir(p["id"]))} for p in items],
                    "queue": analyze_q.qsize() + render_q.qsize(),
                }, ensure_ascii=False)
            return Response(body, mimetype="application/json")
        except RuntimeError:  # pekerja sedang mengubah data clip; coba baca lagi
            time.sleep(0.02)
    return jsonify(error="Server sibuk, coba lagi."), 503


@bp.get("/settings")
def get_settings():
    allset = common.load_settings()
    s = allset[ID]
    s["has_key"] = bool(allset.get("api_key"))  # kuncinya sendiri tidak pernah dikirim ke halaman
    s["gpu"] = {"device": core.transcribe_device(), "error": core.CUDA_ERROR, "encoder": core.video_encoder()}
    return jsonify(s)


@bp.post("/settings")
def post_settings():
    common.update_settings(request.get_json(force=True) or {}, ID)
    return jsonify(ok=True)


@bp.post("/add")
def add_links():
    body = request.get_json(force=True)
    links = [l.strip() for l in re.split(r"[\s,]+", body.get("links", "")) if l.strip().startswith("http")]
    if not links:
        return jsonify(error="Tidak ada link yang valid."), 400
    for url in links:
        p = new_project(url=url, n_clips=body.get("n_clips"), auto_render=body.get("auto_render", False),
                        language=body.get("language"), brief=body.get("brief"), style_id=body.get("style_id"))
        queue_analyze(p["id"])
    return jsonify(ok=True, count=len(links))


@bp.post("/upload")
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Tidak ada file."), 400
    title = os.path.splitext(f.filename)[0]
    p = new_project(title=title, n_clips=request.form.get("n_clips", type=int),
                    auto_render=request.form.get("auto_render") == "true",
                    language=request.form.get("language"), brief=request.form.get("brief"),
                    style_id=request.form.get("style_id"))
    ext = os.path.splitext(f.filename)[1].lower() or ".mp4"
    f.save(os.path.join(pdir(p["id"]), "source" + ext))
    p["source"] = "source" + ext
    save_project(p)
    queue_analyze(p["id"])
    return jsonify(ok=True)


@bp.post("/project/<pid>/retry")
def retry(pid):
    p = projects.get(pid) or abort(404)
    queue_analyze(pid)
    return jsonify(ok=True)


@bp.post("/project/<pid>/reanalyze")
def reanalyze(pid):
    """Cari ulang momen (transkrip dipakai ulang, cepat)."""
    p = projects.get(pid) or abort(404)
    if busy(p):
        return jsonify(error="Tunggu render selesai atau batalkan dulu."), 409
    body = request.get_json(silent=True) or {}
    if body.get("n_clips"):
        p["n_clips"] = int(body["n_clips"])
    if "brief" in body:
        p["brief"] = clean_brief(body["brief"])
    queue_analyze(pid)
    return jsonify(ok=True)


@bp.post("/parse-brief")
def parse_brief():
    """Ringkasan isi kolom referensi (dipakai halaman untuk menunjukkan apa yang dikenali)."""
    b = core.parse_brief(clean_brief((request.get_json(silent=True) or {}).get("text")))
    want, avoid = core.brief_keywords(b["instructions"])
    return jsonify({**b, "keywords": want, "avoid": avoid})


@bp.post("/project/<pid>/cancel")
def cancel(pid):
    """Batalkan analisis dan/atau render. Body {cid} untuk satu clip saja."""
    p = projects.get(pid) or abort(404)
    cid = (request.get_json(silent=True) or {}).get("cid")
    n = 0
    with lock:
        for c in p.get("clips", []):
            if (cid is None or c["id"] == cid) and c.get("render_status") in ("antri", "proses"):
                c["job"] = None
                c["render_status"], c["render_progress"] = None, 0
                n += 1
        if cid is None and p.get("status") in ("antri", "proses"):
            p["job"] = None
            if p.get("clips"):
                p["status"], p["stage"] = "siap", "Pencarian ulang dibatalkan."
            else:
                p["status"], p["stage"] = "gagal", "Dibatalkan. Klik Ulangi untuk memproses lagi."
            n += 1
    save_project(p)
    return jsonify(ok=True, count=n)


@bp.post("/project/<pid>/drop-source")
def drop_source(pid):
    """Hapus video sumber untuk menghemat disk. Hasil render di folder output tetap aman."""
    p = projects.get(pid) or abort(404)
    with lock:
        if busy(p):
            return jsonify(error="Tunggu proses selesai atau batalkan dulu."), 409
        src = p.get("source")
        p["source"] = None
        p["source_removed"] = True
    paths = [os.path.join(pdir(pid), "audio.wav")] + ([os.path.join(pdir(pid), src)] if src else [])
    remove_later(remove_files(*paths))
    save_project(p)
    return jsonify(ok=True)


@bp.delete("/project/<pid>")
def delete_project(pid):
    with lock:
        p = projects.pop(pid, None)
        if p:
            # file yang masih dipakai render akan dibersihkan pekerja setelah ia berhenti
            shutil.rmtree(pdir(pid), ignore_errors=True)
            if os.path.exists(pdir(pid)) and not busy(p):
                remove_later([pdir(pid)])  # mis. video masih terbuka di browser
    return jsonify(ok=True)


@bp.get("/project/<pid>/transcript")
def transcript(pid):
    p = projects.get(pid) or abort(404)
    segs = segments_of(p)
    return jsonify([{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segs])


@bp.post("/project/<pid>/clip")
def upsert_clip(pid):
    p = projects.get(pid) or abort(404)
    body = request.get_json(force=True)
    with lock:
        c = next((x for x in p["clips"] if x["id"] == body.get("id")), None)
        is_new = c is None
        if is_new:
            c = {"id": uuid.uuid4().hex[:8], "selected": True, "render_status": None, "file": None,
                 "score": 0, "reason": "dibuat manual", "hashtags": [], "caption": ""}
        patch = {k: body[k] for k in ("start", "end", "title", "caption", "selected", "hashtags") if k in body}
        try:
            start = max(0.0, float(patch.get("start", c.get("start", 0))))
            end = float(patch.get("end", c.get("end", 0)))
        except (TypeError, ValueError):
            return jsonify(error="Format waktu tidak valid."), 400
        # periksa dulu sebelum mengubah apa pun, supaya nilai salah tidak tersimpan
        if end <= start:
            return jsonify(error="Waktu selesai harus setelah waktu mulai."), 400
        c.update(patch)
        c["start"], c["end"] = start, end
        if is_new:
            p["clips"].append(c)
        segs = segments_of(p)
        c["text"] = " ".join(s["text"] for s in segs if s["end"] > c["start"] and s["start"] < c["end"])
        p["clips"].sort(key=lambda x: x["start"])
    save_project(p)
    return jsonify(ok=True, clip=c)


@bp.get("/project/<pid>/clip/<cid>/subtitle")
def get_subtitle(pid, cid):
    """Teks subtitle clip (dari transkrip), untuk dikoreksi."""
    p = projects.get(pid) or abort(404)
    c = next((x for x in p["clips"] if x["id"] == cid), None) or abort(404)
    return jsonify(text=core.clip_words_text(segments_of(p), c["start"], c["end"]))


@bp.post("/project/<pid>/clip/<cid>/subtitle")
def set_subtitle(pid, cid):
    """Simpan koreksi subtitle ke transkrip proyek (berlaku juga untuk clip lain di bagian yang sama)."""
    p = projects.get(pid) or abort(404)
    text = str((request.get_json(silent=True) or {}).get("text") or "")
    with lock:
        c = next((x for x in p["clips"] if x["id"] == cid), None) or abort(404)
        segs = segments_of(p)
        try:
            changed = core.edit_words(segs, c["start"], c["end"], text)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        if changed:
            with open(os.path.join(pdir(pid), "transcript.json"), "w", encoding="utf-8") as f:
                json.dump(segs, f, ensure_ascii=False)
            for x in p["clips"]:
                x["text"] = " ".join(s["text"] for s in segs if s["end"] > x["start"] and s["start"] < x["end"])
                if x.get("render_status") == "selesai" and x["end"] > c["start"] and x["start"] < c["end"]:
                    x["subs_changed"] = True  # hasil render lama masih memakai teks sebelumnya
    save_project(p)
    return jsonify(ok=True, changed=changed)


@bp.delete("/project/<pid>/clip/<cid>")
def delete_clip(pid, cid):
    p = projects.get(pid) or abort(404)
    with lock:
        for c in p["clips"]:
            if c["id"] == cid:
                c["job"] = None  # hentikan render clip ini bila sedang berjalan
        p["clips"] = [c for c in p["clips"] if c["id"] != cid]
    save_project(p)
    return jsonify(ok=True)


@bp.post("/project/<pid>/render")
def render(pid):
    p = projects.get(pid) or abort(404)
    if not p.get("source"):
        return jsonify(error="Video sumber sudah dihapus, clip tidak bisa dirender lagi."), 409
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or [c["id"] for c in p["clips"] if c.get("selected")]
    if body.get("style"):
        p["style"] = body["style"]
    n = sum(1 for cid in ids if queue_render(pid, cid))
    save_project(p)
    return jsonify(ok=True, count=n)


@bp.post("/render-all")
def render_all():
    n = 0
    for pid, p in list(projects.items()):
        for c in p.get("clips", []):
            if c.get("selected") and c.get("render_status") != "selesai" and queue_render(pid, c["id"]):
                n += 1
    return jsonify(ok=True, count=n)


@bp.post("/preview-style")
def preview_style():
    """Satu frame contoh dengan gaya saat ini, supaya tidak perlu render ulang hanya untuk mencoba gaya."""
    body = request.get_json(silent=True) or {}
    style = {**load_settings()["style"], **(body.get("style") or {})}
    try:
        jpg = preview_jpeg(style, body.get("pid"))
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Pratinjau gagal: {e}"[:300]), 500
    return Response(jpg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@bp.get("/styles")
def list_styles():
    """Gaya saya + preset bawaan + gaya mana yang sedang aktif (dan apakah sudah diubah sejak dipilih)."""
    s = load_settings()
    src = _preview_source()
    mine = [{**x, "thumb": thumb_key(x["style"], src)} for x in load_styles()]
    presets = [{**x, "thumb": thumb_key(x["style"], src)} for x in PRESETS]
    active = find_style(s.get("active_style_id"))
    modified = bool(active) and look_of(s["style"]) != look_of(active["style"])
    return jsonify(styles=mine, presets=presets, active_id=active["id"] if active else "",
                   active_modified=modified, current_thumb=thumb_key(s["style"], src))


@bp.get("/styles/<sid>/thumb")
def style_thumb(sid):
    """Gambar contoh kecil sebuah gaya ("current" = gaya aktif). Disimpan di data/clip/thumbs."""
    if sid == "current":
        style = load_settings()["style"]
    else:
        st = find_style(sid) or abort(404)
        style = st["style"]
    key = thumb_key(style)
    path = os.path.join(THUMBS, key + ".jpg")
    if not os.path.exists(path):
        try:
            jpg = preview_jpeg({**DEFAULT_STYLE, **style}, width=THUMB_W)
        except Exception as e:
            traceback.print_exc()
            return jsonify(error=f"Gambar gaya gagal dibuat: {e}"[:300]), 500
        os.makedirs(THUMBS, exist_ok=True)
        files = sorted((e for e in os.scandir(THUMBS) if e.name.endswith(".jpg")), key=lambda e: e.stat().st_mtime)
        remove_files(*[e.path for e in files[:-300]])  # simpan paling banyak ~300 gambar
        tmp = f"{path}.{uuid.uuid4().hex[:6]}.tmp"
        with open(tmp, "wb") as f:
            f.write(jpg)
        try:
            os.replace(tmp, path)
        except OSError:  # gambar yang sama sedang ditulis/dikirim permintaan lain: kirim hasil buatan sendiri
            remove_files(tmp)
            return Response(jpg, mimetype="image/jpeg")
    return send_from_directory(THUMBS, key + ".jpg", max_age=31536000 if request.args.get("k") == key else 0)


@bp.post("/styles")
def create_style():
    """Simpan gaya aktif sekarang ke "Gaya saya"."""
    body = request.get_json(silent=True) or {}
    s = load_settings()
    entry = add_style(body.get("name"), s["style"], source={"kind": "manual"})
    common.update_settings({"active_style_id": entry["id"]}, ID)
    return jsonify(ok=True, style=entry)


@bp.post("/styles/<sid>")
def update_style(sid):
    """Ganti nama (name) dan/atau timpa isinya dengan gaya aktif sekarang (overwrite: true)."""
    body = request.get_json(silent=True) or {}
    with styles_lock:
        items = load_styles()
        x = next((i for i in items if i["id"] == sid), None) or abort(404)
        if "name" in body:
            x["name"] = clean_style_name(body["name"], x["name"])
        if body.get("overwrite"):
            x["style"] = look_of(load_settings()["style"])
            x["updated"] = int(time.time())
        save_styles(items)
    return jsonify(ok=True, style=x)


@bp.delete("/styles/<sid>")
def delete_style(sid):
    with styles_lock:
        save_styles([x for x in load_styles() if x["id"] != sid])
    with lock:
        for p in projects.values():
            if p.get("style_id") == sid:  # proyek kembali memakai gaya aktif
                p["style_id"] = None
                save_project(p)
    if load_settings().get("active_style_id") == sid:
        common.update_settings({"active_style_id": ""}, ID)
    return jsonify(ok=True)


@bp.post("/styles/<sid>/apply")
def apply_style(sid):
    """Jadikan gaya ini gaya aktif (watermark & perataan volume milik pengguna tidak berubah)."""
    st = find_style(sid) or abort(404)
    s = load_settings()
    new = apply_look(s["style"], st["style"])
    common.update_settings({"style": new, "active_style_id": st["id"]}, ID)
    return jsonify(ok=True, style=new)


@bp.post("/project/<pid>/style")
def set_project_style(pid):
    """Gaya khusus proyek ini (dari pustaka). Kosong = ikut gaya aktif."""
    p = projects.get(pid) or abort(404)
    sid = (request.get_json(silent=True) or {}).get("style_id") or None
    if sid and not find_style(sid):
        return jsonify(error="Gaya tidak ditemukan."), 404
    with lock:
        p["style_id"] = sid
    save_project(p)
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# Baca gaya dari clip referensi (pengukuran piksel + AI lokal gratis), di latar belakang
# --------------------------------------------------------------------------
style_jobs: dict[str, dict] = {}
_style_slot = threading.Semaphore(1)   # satu pembacaan dalam satu waktu (model AI memakai banyak memori)


def _run_style_job(jid, url, path, title, use_ai, replace_id):
    job = style_jobs[jid]
    tmp = os.path.join(DATA, "style_ref", jid)

    def alive():
        if job["cancel"]:
            raise Cancelled()

    def stage(label, x):
        alive()
        job["stage"], job["progress"] = label, round(x, 3)

    try:
        stage("Menunggu giliran...", 0.01)
        with _style_slot:
            s = load_settings()
            if url:
                stage("Mengunduh clip referensi...", 0.05)
                info = core.download_reference(url, tmp, s.get("cookies_browser") or None, video=True)
                path, title = info["path"], info["title"]
            res = style_ai.analyze(path, ai=s, use_ai=use_ai and s.get("local_ai_on", True), stage=stage,
                                   alive=alive)
        alive()
        # gaya lengkap: yang terbaca menimpa gaya aktif sekarang, sisanya tetap
        detected = res["style"]
        full = look_of({**load_settings()["style"], **detected})
        ai = res.get("ai") or {}
        meta = {"source": {"kind": "referensi", "title": str(title or "")[:150], "url": url or ""},
                "detected": sorted(detected), "sources": res["sources"], "summary": ai.get("summary", ""),
                "ai_model": ai.get("model", ""), "ai_provider": ai.get("provider", ""), "notes": res["notes"]}
        entry = None
        if replace_id:
            with styles_lock:
                items = load_styles()
                entry = next((x for x in items if x["id"] == replace_id), None)
                if entry:
                    entry.update(style=full, updated=int(time.time()), **meta)
                    save_styles(items)
        if not entry:
            name = style_ai.style_name(ai.get("name", ""), full) if ai else ""
            entry = add_style(name or str(title or "Gaya referensi")[:40], full, **meta)
        job.update(status="selesai", progress=1, stage="Selesai",
                   result={**res, "title": title, "style_id": entry["id"], "name": entry["name"],
                           "style": full, "detected": sorted(detected)})
    except Cancelled:
        job.update(status="batal", stage="Dibatalkan")
    except Exception as e:
        traceback.print_exc()
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        job.update(status="gagal", error=f"Gagal membaca clip referensi: {msg}"[:400])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(tmp):
            remove_later([tmp])


@bp.post("/style-jobs")
def start_style_job():
    """Mulai membaca gaya dari link atau file clip referensi. Hasilnya otomatis masuk "Gaya saya".
    Body: {url, use_ai, replace_id} atau multipart (file, use_ai)."""
    jid = uuid.uuid4().hex[:10]
    tmp = os.path.join(DATA, "style_ref", jid)
    f = request.files.get("file")
    body = request.form if f else (request.get_json(silent=True) or {})
    use_ai = str(body.get("use_ai", "true")).lower() not in ("false", "0", "")
    replace_id = body.get("replace_id") or None
    url, path, title = None, None, None
    if f:
        os.makedirs(tmp, exist_ok=True)
        path = os.path.join(tmp, "ref" + (os.path.splitext(f.filename or "")[1].lower() or ".mp4"))
        f.save(path)
        title = os.path.splitext(f.filename or "file")[0]
    else:
        url = str(body.get("url") or "").strip()
        if not url.startswith("http"):
            return jsonify(error="Tempel link clip referensi atau pilih file video."), 400
    for old in sorted(style_jobs, key=lambda k: style_jobs[k]["created"])[:-20]:
        if style_jobs[old]["status"] != "proses":
            style_jobs.pop(old, None)
    style_jobs[jid] = {"id": jid, "status": "proses", "stage": "Menunggu giliran...", "progress": 0,
                       "error": "", "result": None, "cancel": False, "created": time.time(),
                       "label": url or title}
    threading.Thread(target=_run_style_job, args=(jid, url, path, title, use_ai, replace_id), daemon=True).start()
    return jsonify(ok=True, id=jid)


@bp.get("/style-jobs/<jid>")
def get_style_job(jid):
    job = style_jobs.get(jid) or abort(404)
    return jsonify({k: v for k, v in job.items() if k != "cancel"})


@bp.post("/style-jobs/<jid>/cancel")
def cancel_style_job(jid):
    job = style_jobs.get(jid) or abort(404)
    job["cancel"] = True
    return jsonify(ok=True)


@bp.get("/fonts/<key>")
def font_file(key):
    """Berkas font subtitle, supaya pilihan font di halaman tampil dengan bentuk aslinya."""
    if key not in core.CAPTION_FONTS:
        abort(404)
    file = core.CAPTION_FONTS[key][0]
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for d in (core.FONTS_DIR, win):
        if os.path.isfile(os.path.join(d, file)):
            return send_from_directory(d, file, mimetype="font/ttf", max_age=86400)
    abort(404)


@bp.get("/media/<pid>/<path:name>")
def media(pid, name):
    if pid not in projects:  # cegah pid seperti ".." membuka folder data/
        abort(404)
    return send_from_directory(pdir(pid), name, conditional=True)


# --------------------------------------------------------------------------
# Dipanggil app.py
# --------------------------------------------------------------------------
LEGACY_KEYS = ("whisper_model", "language", "n_clips", "min_len", "max_len", "auto_render", "style")


def migrate_legacy():
    """ClipMaker versi lama menyimpan pengaturan clip di tingkat atas settings.json, proyek di
    data/projects, dan hasil render langsung di output/. Sekarang semuanya ada di folder fitur clip.
    Aman dijalankan setiap kali aplikasi dibuka: bila sudah dipindah, tidak ada yang dilakukan."""
    raw = common.read_settings_file()
    old = {k: raw.pop(k) for k in LEGACY_KEYS if k in raw}
    if old:
        raw[ID] = {**old, **(raw.get(ID) if isinstance(raw.get(ID), dict) else {})}
        common.write_settings_file(raw)

    # selama penanda ini ada, isi output/ yang bukan folder fitur adalah hasil render versi lama
    pending = os.path.join(DATA, ".pindah-hasil")
    legacy = os.path.join(common.DATA, "projects")
    if os.path.isdir(legacy):
        open(pending, "w").close()
        failed = common.move_children(legacy, PROJ)
        if failed:
            print(f"  [clip] {len(failed)} proyek lama belum bisa dipindah (berkasnya sedang dibuka?). "
                  "Akan dicoba lagi saat aplikasi dibuka berikutnya.")
        else:
            try:
                os.rmdir(legacy)
            except OSError:
                pass
    shutil.rmtree(os.path.join(common.DATA, "style_ref"), ignore_errors=True)  # sisa berkas sementara

    if os.path.exists(pending):
        failed = common.move_children(common.OUTPUT, OUTPUT, skip=set(common.registered_features()))
        if failed:
            print(f"  [clip] {len(failed)} folder hasil lama belum bisa dipindah ke output/{ID} "
                  "(sedang dibuka?). Akan dicoba lagi saat aplikasi dibuka berikutnya.")
        elif not os.path.isdir(legacy):
            os.remove(pending)


def start():
    """Siapkan fitur: pindahkan data versi lama, muat proyek, jalankan pekerja."""
    migrate_legacy()
    load_projects()
    threading.Thread(target=worker, args=(analyze_q, "analyze"), daemon=True).start()
    threading.Thread(target=worker, args=(render_q, "render"), daemon=True).start()


def summary():
    """Ringkasan untuk kartu fitur di Beranda."""
    for _ in range(5):
        try:
            with lock:
                ps = list(projects.values())
                clips = [c for p in ps for c in p.get("clips", [])]
                return {
                    "busy": sum(1 for p in ps if busy(p)),
                    "queue": analyze_q.qsize() + render_q.qsize(),
                    "stats": [
                        {"label": "Video diproses", "value": len(ps)},
                        {"label": "Momen ditemukan", "value": len(clips)},
                        {"label": "Clip siap upload",
                         "value": sum(1 for c in clips if c.get("render_status") == "selesai")},
                    ],
                }
        except RuntimeError:  # pekerja sedang mengubah daftar clip; coba lagi
            time.sleep(0.02)
    return {"busy": 0, "queue": 0, "stats": []}
