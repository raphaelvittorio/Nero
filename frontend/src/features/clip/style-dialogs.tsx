"use client";

import {
  AlertTriangleIcon,
  ExternalLinkIcon,
  Loader2Icon,
  RotateCwIcon,
  SaveIcon,
  SparklesIcon,
  Trash2Icon,
  UploadIcon,
  WandSparklesIcon,
  XIcon,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { CommitInput } from "@/components/fields";
import { styleAI, useNero } from "@/components/nero/store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api, post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { API } from "./api";
import { STYLE_GROUPS } from "./options";
import { DetectedList, SaveStyleDialog, StyleControl, StylePreview, StyleThumb } from "./style-parts";
import { useStyles } from "./style-store";
import { useStore } from "./store";
import type { Style, StyleEntry } from "./types";

/* ------------------------------ atur detail gaya ------------------------------ */
export function StyleEditorDialog() {
  const { editorOpen, setEditorOpen } = useStyles();
  return (
    <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
      <DialogContent className="max-h-[94vh] gap-0 overflow-hidden p-0 sm:max-w-5xl">
        {editorOpen && <Editor />}
      </DialogContent>
    </Dialog>
  );
}

function Editor() {
  const { settings, patchStyle } = useStore();
  const { library, find, activeName, loadLibrary, setEditorOpen } = useStyles();
  const [tab, setTab] = useState(STYLE_GROUPS[0].id);
  const [saveNew, setSaveNew] = useState(false);
  if (!settings) return null;
  const style = settings.style;
  const group = STYLE_GROUPS.find((g) => g.id === tab) ?? STYLE_GROUPS[0];
  const active = find(settings.active_style_id);
  const canOverwrite = active && !active.preset && library?.active_modified;

  async function overwrite() {
    if (!active) return;
    try {
      await post(`${API}/styles/${active.id}`, { overwrite: true });
      await loadLibrary();
      toast.success(`Perubahan disimpan ke "${active.name}"`);
    } catch {}
  }

  return (
    <div className="grid max-h-[94vh] grid-cols-1 md:h-[min(94vh,700px)] md:grid-cols-[minmax(0,1fr)_17rem]">
      <div className="flex min-h-0 min-w-0 flex-col">
        <DialogHeader className="border-b px-5 pt-5 pb-3">
          <DialogTitle>Atur gaya video</DialogTitle>
          <DialogDescription>
            Mengubah gaya aktif <b className="text-foreground">{activeName}</b>. Tersimpan otomatis dan langsung
            terlihat di pratinjau.
          </DialogDescription>
          <div className="mt-2 flex gap-0.5 overflow-x-auto rounded-lg bg-muted p-0.5 text-xs" role="tablist">
            {STYLE_GROUPS.map((g) => (
              <button
                key={g.id}
                type="button"
                role="tab"
                aria-selected={tab === g.id}
                onClick={() => setTab(g.id)}
                className={cn(
                  "flex-1 rounded-md px-2.5 py-1.5 font-medium whitespace-nowrap text-muted-foreground transition-colors",
                  tab === g.id && "bg-background text-foreground shadow-sm",
                )}
              >
                {g.label}
              </button>
            ))}
          </div>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-1 gap-x-4 gap-y-3.5 sm:grid-cols-2">
            {group.fields.map((f) => (
              <StyleControl
                key={f.key}
                field={f}
                style={style}
                onChange={(k, v) => patchStyle({ [k]: v } as Partial<Style>)}
              />
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t px-5 py-3">
          {canOverwrite && (
            <Button size="sm" onClick={overwrite}>
              <SaveIcon /> Simpan ke &ldquo;{active.name}&rdquo;
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setSaveNew(true)}>
            <SaveIcon /> Simpan sebagai gaya baru
          </Button>
          <div className="flex-1" />
          <Button size="sm" variant="ghost" onClick={() => setEditorOpen(false)}>
            Selesai
          </Button>
        </div>
      </div>
      <aside className="hidden overflow-y-auto border-l bg-muted/40 p-4 md:block">
        <StylePreview style={style} />
      </aside>
      <SaveStyleDialog open={saveNew} onClose={() => setSaveNew(false)} />
    </div>
  );
}

/* ------------------------------ tiru gaya dari clip ------------------------------ */
export function ReferenceDialog() {
  const { refOpen, setRefOpen } = useStyles();
  return (
    <Dialog open={refOpen} onOpenChange={setRefOpen}>
      <DialogContent className="max-h-[94vh] overflow-y-auto sm:max-w-3xl">{refOpen && <ReferenceBody />}</DialogContent>
    </Dialog>
  );
}

function ReferenceBody() {
  const { job, clearJob } = useStyles();
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <WandSparklesIcon className="size-4" /> Tiru gaya dari clip
        </DialogTitle>
        <DialogDescription>
          Nero mengukur subtitle, judul, tata letak & zoom dari piksel video, lalu AI gratis (Gemini atau AI lokal)
          menilai font, cara menyorot kata, animasi, dan nuansa warnanya. Hasilnya otomatis tersimpan di Gaya saya.
        </DialogDescription>
      </DialogHeader>
      {!job || job.status === "batal" ? (
        <ReferenceForm />
      ) : job.status === "proses" ? (
        <JobProgress />
      ) : job.status === "gagal" ? (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/40 p-4">
          <p className="flex items-start gap-2 text-sm text-destructive">
            <AlertTriangleIcon className="mt-0.5 size-4 flex-none" /> {job.error}
          </p>
          <Button size="sm" variant="outline" onClick={clearJob}>
            <RotateCwIcon /> Coba clip lain
          </Button>
        </div>
      ) : (
        <JobResult />
      )}
    </>
  );
}

function ReferenceForm() {
  const { startJob } = useStyles();
  const { localAI, setSettingsOpen } = useNero();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const fileIn = useRef<HTMLInputElement>(null);
  const ai = styleAI(localAI);
  const ready = ai.ready;
  const wantsGemini = localAI?.provider === "gemini";

  async function go(body: { url: string } | FormData) {
    setBusy(true);
    try {
      await startJob(body);
      setUrl("");
    } catch {
    } finally {
      setBusy(false);
      if (fileIn.current) fileIn.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Input
          autoFocus
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && url.trim() && !busy && go({ url: url.trim() })}
          placeholder="https://www.tiktok.com/@akun/video/..."
          className="h-9 min-w-0 flex-1 basis-60"
          aria-label="Link clip referensi"
        />
        <Button className="h-9" disabled={!url.trim() || busy} onClick={() => go({ url: url.trim() })}>
          <SparklesIcon /> Baca gaya
        </Button>
        <Button variant="outline" className="h-9" disabled={busy} onClick={() => fileIn.current?.click()}>
          <UploadIcon /> Pilih file
        </Button>
        <input
          ref={fileIn}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const fd = new FormData();
            fd.append("file", f);
            go(fd);
          }}
        />
      </div>
      <div
        className={cn(
          "flex items-start gap-3 rounded-xl border p-3 text-xs",
          ready ? "border-ok/40" : "border-warn/40",
        )}
      >
        <span className={cn("mt-1 size-2 flex-none rounded-full", ready ? "bg-ok" : "bg-warn")} />
        <div className="min-w-0 flex-1">
          {ai.kind === "gemini" ? (
            <p>
              <b>Gemini siap</b> ({localAI?.gemini.model}). Gemini menonton 20 detik pertama clip, biasanya selesai
              dalam 20–40 detik. Clip dikirim ke Google; bila kuota gratis habis, Nero memakai AI lokal.
            </p>
          ) : ai.kind === "lokal" ? (
            <p>
              <b>AI lokal siap</b> ({localAI?.chosen}).{" "}
              {wantsGemini ? "Gemini dipilih tetapi API key-nya belum diisi. " : ""}
              Pertama kali membaca bisa 1–3 menit selagi model dimuat, berikutnya lebih cepat.
            </p>
          ) : localAI && !localAI.on ? (
            <p>
              <b>AI dimatikan.</b> Gaya tetap dibaca dari piksel (ukuran, posisi, warna, judul, zoom), tetapi font &
              cara menyorot kata tidak ditiru.
            </p>
          ) : (
            <p>
              <b>AI belum siap</b>
              {wantsGemini ? ": API key Gemini belum diisi." : localAI?.status.ok ? ": belum ada model yang bisa melihat gambar." : ": Ollama belum berjalan."}{" "}
              Gaya tetap dibaca dari piksel, tetapi font & cara menyorot kata tidak ditiru. Siapkan sekali saja, gratis.
            </p>
          )}
        </div>
        {(!ready || (wantsGemini && ai.kind !== "gemini")) && (
          <Button size="xs" variant="outline" onClick={() => setSettingsOpen(true)}>
            Siapkan AI
          </Button>
        )}
      </div>
      <ul className="grid gap-1.5 text-xs text-muted-foreground sm:grid-cols-2">
        <li>✓ Pakai clip pendek vertikal (TikTok / Reels / Shorts) yang bersubtitle.</li>
        <li>
          {ai.kind === "gemini"
            ? "✓ Hanya potongan kecil clip (20 detik, tanpa suara) yang dikirim ke Gemini."
            : "✓ Dibaca di komputer Anda; video tidak dikirim ke layanan AI mana pun."}
        </li>
        <li>✓ Semua hasil bacaan tersimpan di Gaya saya, bisa dipilih kapan saja.</li>
        <li>✗ Musik, b-roll, stiker & emoji tidak ikut ditiru.</li>
      </ul>
    </div>
  );
}

function JobProgress() {
  const { job, cancelJob } = useStyles();
  if (!job) return null;
  return (
    <div className="flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex items-center gap-2 text-sm">
        <Loader2Icon className="size-4 animate-spin" />
        <span className="min-w-0 flex-1">{job.stage}</span>
        <span className="text-xs text-muted-foreground tabular-nums">{Math.round(job.progress * 100)}%</span>
      </div>
      <Progress value={job.progress * 100} />
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex-1 text-xs text-muted-foreground">
          Jendela ini boleh ditutup; pembacaan tetap berjalan dan hasilnya masuk Gaya saya.
        </p>
        <Button size="sm" variant="outline" onClick={cancelJob}>
          <XIcon /> Batal
        </Button>
      </div>
    </div>
  );
}

function JobResult() {
  const { job, clearJob, apply, loadLibrary, setRefOpen } = useStyles();
  const { settings } = useStore();
  const { setSettingsOpen } = useNero();
  const [name, setName] = useState(job?.result?.name ?? "");
  const r = job?.result;
  if (!r || !settings) return null;
  const preview = { ...settings.style, ...r.style } as Style;

  async function rename(v: string) {
    try {
      const res = await post<{ ok: boolean; style: { name: string } }>(`${API}/styles/${r!.style_id}`, { name: v });
      setName(res.style.name);
      loadLibrary();
    } catch {}
  }

  return (
    <div className="grid gap-5 sm:grid-cols-[13rem_1fr]">
      <StylePreview style={preview} className="mx-auto w-48 sm:w-full" />
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Nama gaya (tersimpan di Gaya saya)</span>
          <CommitInput value={name} onCommit={rename} maxLength={40} className="h-9 font-semibold" />
          <span className="truncate text-[11px] text-muted-foreground" title={r.title}>
            Dari &ldquo;{r.title}&rdquo; · {r.seconds} detik pertama dibaca
          </span>
        </div>
        {r.ai ? (
          <div className="rounded-lg bg-muted/70 p-3 text-xs">
            <p className="mb-1 flex items-center gap-1.5 font-semibold">
              <SparklesIcon className="size-3.5" /> Kata {r.ai.provider === "gemini" ? "Gemini" : "AI lokal"} ({r.ai.model})
            </p>
            <p className="text-muted-foreground">{r.ai.summary || "Tidak ada ringkasan."}</p>
          </div>
        ) : (
          <div className="flex items-start gap-2 rounded-lg border border-warn/40 p-3 text-xs">
            <AlertTriangleIcon className="mt-0.5 size-3.5 flex-none text-warn" />
            <p className="flex-1 text-muted-foreground">
              Dibaca tanpa AI: font & cara menyorot kata memakai pengaturan Anda sekarang.{" "}
              {r.ai_missing && (
                <button
                  type="button"
                  onClick={() => setSettingsOpen(true)}
                  className="font-medium text-foreground underline underline-offset-4"
                >
                  Siapkan AI
                </button>
              )}
            </p>
          </div>
        )}
        <DetectedList style={r.style} keys={r.detected} sources={r.sources} />
        {r.notes.length > 0 && (
          <ul className="flex flex-col gap-0.5 text-[11px] text-muted-foreground">
            {r.notes.map((n) => (
              <li key={n}>• {n}</li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            onClick={async () => {
              await apply(r.style_id);
              clearJob();
              setRefOpen(false);
            }}
          >
            Pakai gaya ini
          </Button>
          <Button variant="outline" onClick={clearJob}>
            Baca clip lain
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              clearJob();
              setRefOpen(false);
            }}
          >
            Nanti saja
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------ detail satu gaya ------------------------------ */
export function StyleDetailDialog() {
  const { detail, setDetail } = useStyles();
  return (
    <Dialog open={detail !== null} onOpenChange={(o) => !o && setDetail(null)}>
      <DialogContent className="max-h-[94vh] overflow-y-auto sm:max-w-2xl">
        {detail && <Detail key={detail.id} s={detail} />}
      </DialogContent>
    </Dialog>
  );
}

function Detail({ s }: { s: StyleEntry }) {
  const { settings } = useStore();
  const { apply, setDetail, loadLibrary, library, startJob, setRefOpen } = useStyles();
  const { localAI } = useNero();
  const { confirm } = useStore();
  const [name, setName] = useState(s.name);
  const active = library?.active_id === s.id;
  const url = s.source?.url;

  async function rename(v: string) {
    try {
      const r = await post<{ ok: boolean; style: { name: string } }>(`${API}/styles/${s.id}`, { name: v });
      setName(r.style.name);
      loadLibrary();
    } catch {}
  }

  async function remove() {
    const ok = await confirm({
      title: `Hapus gaya "${name}"?`,
      description: "Video yang memakai gaya ini akan kembali memakai gaya aktif. Hasil render tetap aman.",
      action: "Hapus",
      destructive: true,
    });
    if (!ok) return;
    try {
      await api(`${API}/styles/${s.id}`, { method: "DELETE" });
      await loadLibrary();
      setDetail(null);
      toast.success("Gaya dihapus");
    } catch {}
  }

  async function reread() {
    if (!url) return;
    try {
      await startJob({ url, replace_id: s.id });
      setDetail(null);
      setRefOpen(true);
    } catch {}
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex flex-wrap items-center gap-2 pr-8">
          {s.preset ? name : "Detail gaya"}
          {s.preset && <Badge variant="secondary">Siap pakai</Badge>}
          {active && <Badge variant="outline">Sedang dipakai</Badge>}
        </DialogTitle>
        <DialogDescription>
          {s.preset
            ? "Gaya bawaan Nero. Pakai lalu ubah sesuai selera, kemudian simpan sebagai gaya Anda."
            : s.source?.kind === "referensi"
              ? `Dibaca dari clip referensi${s.ai_model ? ` dengan ${s.ai_provider === "gemini" ? "Gemini" : "AI lokal"} (${s.ai_model})` : " tanpa AI"}.`
              : "Disimpan dari pengaturan gaya Anda."}
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-5 sm:grid-cols-[10rem_1fr]">
        <StyleThumb id={s.id} k={s.thumb} className="mx-auto w-40" />
        <div className="flex min-w-0 flex-col gap-3">
          {!s.preset && (
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Nama</span>
              <CommitInput value={name} onCommit={rename} maxLength={40} className="h-9 font-semibold" />
            </div>
          )}
          {s.summary && <p className="text-sm text-muted-foreground">{s.summary}</p>}
          {s.source?.kind === "referensi" && (
            <p className="truncate text-xs text-muted-foreground" title={s.source.title}>
              Sumber:{" "}
              {url ? (
                <a href={url} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-4">
                  {s.source.title || url} <ExternalLinkIcon className="inline size-3" />
                </a>
              ) : (
                <span className="text-foreground">{s.source.title || "file"}</span>
              )}
            </p>
          )}
          {s.detected?.length ? (
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium">Yang terbaca dari clip</span>
              <DetectedList style={{ ...settings?.style, ...s.style }} keys={s.detected} sources={s.sources} />
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-1">
            {!active && (
              <Button
                onClick={async () => {
                  await apply(s.id);
                  setDetail(null);
                }}
              >
                Pakai gaya ini
              </Button>
            )}
            {url && !s.preset && (
              <Button
                variant="outline"
                onClick={reread}
                title={styleAI(localAI).ready ? `Baca ulang clip ini dengan ${styleAI(localAI).label}` : "Baca ulang clip ini"}
              >
                <RotateCwIcon /> Baca ulang{styleAI(localAI).ready && !s.ai_model ? " dengan AI" : ""}
              </Button>
            )}
            {!s.preset && (
              <Button variant="ghost" className="text-destructive" onClick={remove}>
                <Trash2Icon /> Hapus
              </Button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
