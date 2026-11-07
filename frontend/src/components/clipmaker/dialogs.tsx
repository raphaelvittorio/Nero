"use client";

import { SearchIcon, TrashIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, fmt, post } from "@/lib/api";
import { COOKIE_BROWSERS, LANGUAGES, WHISPER_MODELS } from "@/lib/options";
import type { Language, Settings, TranscriptLine } from "@/lib/types";
import { cn } from "@/lib/utils";

import { BriefField } from "./brief-field";
import { SimpleSelect } from "./fields";
import { useStore } from "./store";

/* ------------------------------ pemutar ------------------------------ */
export function PlayerDialog() {
  const { player, setPlayer } = useStore();
  const stopAt = useRef<number | null>(null);
  const vertical = player?.mode === "result";

  return (
    <Dialog open={player !== null} onOpenChange={(open) => !open && setPlayer(null)}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="pr-8">
            {player?.mode === "preview" ? `Pratinjau: ${player.title}` : player?.title}
          </DialogTitle>
        </DialogHeader>
        {player && (
          <video
            key={player.src + player.mode}
            src={player.src}
            controls
            playsInline
            autoPlay={player.mode === "result"}
            className={cn(
              "rounded-lg bg-black",
              vertical ? "mx-auto h-[70vh] w-auto max-w-full" : "max-h-[70vh] w-full",
            )}
            onLoadedMetadata={(e) => {
              if (player.mode !== "preview") return;
              stopAt.current = player.end;
              e.currentTarget.currentTime = player.start;
              e.currentTarget.play().catch(() => {});
            }}
            onTimeUpdate={(e) => {
              if (stopAt.current !== null && e.currentTarget.currentTime >= stopAt.current) {
                e.currentTarget.pause();
                stopAt.current = null;
              }
            }}
          />
        )}
        <DialogDescription>
          {player?.mode === "preview"
            ? `${fmt(player.start)} → ${fmt(player.end)} (bagian dari video asli, sebelum di-render)`
            : "Hasil akhir 1080×1920"}
        </DialogDescription>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------ transkrip ------------------------------ */
export function TranscriptDialog() {
  const { transcriptPid, setTranscriptPid } = useStore();
  return (
    <Dialog open={transcriptPid !== null} onOpenChange={(open) => !open && setTranscriptPid(null)}>
      <DialogContent className="sm:max-w-2xl">
        {transcriptPid && <TranscriptBody key={transcriptPid} pid={transcriptPid} />}
      </DialogContent>
    </Dialog>
  );
}

function TranscriptBody({ pid }: { pid: string }) {
  const { setTranscriptPid, refresh } = useStore();
  const [lines, setLines] = useState<TranscriptLine[] | null>(null);
  const [q, setQ] = useState("");
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    api<TranscriptLine[]>(`/api/project/${pid}/transcript`)
      .then((l) => alive && setLines(l))
      .catch(() => alive && setTranscriptPid(null));
    return () => {
      alive = false;
    };
  }, [pid, setTranscriptPid]);

  const lo = a === null ? -1 : Math.min(a, b ?? a);
  const hi = a === null ? -1 : Math.max(a, b ?? a);
  const query = q.trim().toLowerCase();
  const shown = useMemo(
    () => (lines ?? []).map((l, i) => [l, i] as const).filter(([l]) => !query || l.text.toLowerCase().includes(query)),
    [lines, query],
  );

  function pick(i: number) {
    if (a === null || b !== null) {
      setA(i);
      setB(null);
    } else setB(i);
  }

  async function makeClip() {
    if (!lines || a === null) {
      toast("Pilih kalimat dulu");
      return;
    }
    const title = lines[lo].text.split(/\s+/).slice(0, 8).join(" ");
    try {
      await post(`/api/project/${pid}/clip`, { start: lines[lo].start, end: lines[hi].end, title });
      setTranscriptPid(null);
      toast.success("Clip baru ditambahkan");
      refresh();
    } catch {}
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Transkrip</DialogTitle>
        <DialogDescription>
          Klik satu kalimat sebagai awal, lalu klik kalimat lain sebagai akhir, kemudian tekan{" "}
          <b className="text-foreground">Jadikan clip</b>.
        </DialogDescription>
      </DialogHeader>
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari kata..." className="pl-8" />
      </div>
      <div className="max-h-[52vh] overflow-auto pr-1">
        {lines === null && <p className="py-8 text-center text-muted-foreground">Memuat transkrip...</p>}
        {shown.map(([l, i]) => (
          <button
            key={i}
            type="button"
            onClick={() => pick(i)}
            className={cn(
              "flex w-full gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-muted",
              i >= lo && i <= hi && "bg-primary/12 hover:bg-primary/18",
            )}
          >
            <b className="min-w-16 font-semibold text-primary tabular-nums">{fmt(l.start)}</b>
            <span>{l.text}</span>
          </button>
        ))}
      </div>
      <DialogFooter className="items-center sm:justify-between">
        <span className="text-xs text-muted-foreground">
          {lines && a !== null
            ? `${fmt(lines[lo].start)} → ${fmt(lines[hi].end)} (${(lines[hi].end - lines[lo].start).toFixed(0)} dtk)`
            : "Belum ada pilihan"}
        </span>
        <Button onClick={makeClip}>Jadikan clip</Button>
      </DialogFooter>
    </>
  );
}

/* ------------------------------ pengaturan ------------------------------ */
export function SettingsDialog() {
  const { settings, settingsOpen, setSettingsOpen } = useStore();
  return (
    <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
      <DialogContent className="sm:max-w-2xl">
        {settings && settingsOpen && <SettingsForm settings={settings} />}
      </DialogContent>
    </Dialog>
  );
}

function SettingsForm({ settings }: { settings: Settings }) {
  const { setSettingsOpen, loadSettings } = useStore();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(settings.ai_model);
  const [whisper, setWhisper] = useState(settings.whisper_model);
  const [language, setLanguage] = useState<Language>(settings.language);
  const [n, setN] = useState(settings.n_clips);
  const [min, setMin] = useState(settings.min_len);
  const [max, setMax] = useState(settings.max_len);
  const [cookie, setCookie] = useState(settings.cookies_browser || "none");

  async function save() {
    if (max <= min) {
      toast.error("Durasi maks harus lebih besar dari minimum");
      return;
    }
    try {
      await post("/api/settings", {
        api_key: key,
        ai_model: model.trim(),
        whisper_model: whisper,
        language,
        n_clips: n,
        min_len: min,
        max_len: max,
        cookies_browser: cookie === "none" ? "" : cookie,
      });
      setSettingsOpen(false);
      await loadSettings();
      toast.success("Pengaturan disimpan");
    } catch {}
  }

  async function clearKey() {
    try {
      await post("/api/settings", { clear_key: true });
      setSettingsOpen(false);
      await loadSettings();
      toast.success("API key dihapus");
    } catch {}
  }

  const field = "flex flex-col gap-1.5";
  return (
    <>
      <DialogHeader>
        <DialogTitle>Pengaturan</DialogTitle>
      </DialogHeader>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className={cn(field, "sm:col-span-2")}>
          <Label htmlFor="s_key">
            Claude API key (opsional — membuat pemilihan momen, judul & caption jauh lebih pintar)
          </Label>
          <Input
            id="s_key"
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-ant-..."
          />
          <span className={cn("text-xs", settings.has_key ? "text-ok" : "text-muted-foreground")}>
            {settings.has_key
              ? "✓ API key tersimpan. Kosongkan untuk tetap memakai yang lama."
              : "Belum ada API key."}
          </span>
        </div>
        <div className={field}>
          <Label htmlFor="s_model">Model AI</Label>
          <Input id="s_model" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div className={field}>
          <Label>Model transkrip</Label>
          <SimpleSelect value={whisper} onChange={setWhisper} options={WHISPER_MODELS} aria-label="Model transkrip" />
        </div>
        <div className={field}>
          <Label>Bahasa video</Label>
          <SimpleSelect value={language} onChange={setLanguage} options={LANGUAGES} aria-label="Bahasa video" />
        </div>
        <div className={field}>
          <Label htmlFor="s_n">Jumlah clip default</Label>
          <Input id="s_n" type="number" min={1} max={20} value={n} onChange={(e) => setN(Number(e.target.value))} />
        </div>
        <div className={field}>
          <Label htmlFor="s_min">Durasi min (detik)</Label>
          <Input id="s_min" type="number" min={5} max={180} value={min} onChange={(e) => setMin(Number(e.target.value))} />
        </div>
        <div className={field}>
          <Label htmlFor="s_max">Durasi maks (detik)</Label>
          <Input id="s_max" type="number" min={10} max={180} value={max} onChange={(e) => setMax(Number(e.target.value))} />
        </div>
        <div className={cn(field, "sm:col-span-2")}>
          <Label>
            Ambil cookies dari browser (isi bila YouTube minta login / &ldquo;confirm you&rsquo;re not a bot&rdquo;)
          </Label>
          <SimpleSelect value={cookie} onChange={setCookie} options={COOKIE_BROWSERS} aria-label="Cookies browser" />
        </div>
      </div>
      <DialogFooter className="sm:justify-between">
        <Button variant="destructive" size="sm" onClick={clearKey} disabled={!settings.has_key}>
          <TrashIcon /> Hapus API key
        </Button>
        <Button onClick={save}>Simpan</Button>
      </DialogFooter>
    </>
  );
}

/* ------------------------------ cari ulang momen ------------------------------ */
export function ReanalyzeDialog({ pid, onClose }: { pid: string | null; onClose: () => void }) {
  return (
    <Dialog open={pid !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        {pid && <ReanalyzeForm key={pid} pid={pid} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function ReanalyzeForm({ pid, onClose }: { pid: string; onClose: () => void }) {
  const { project, settings, refresh } = useStore();
  const [n, setN] = useState(project(pid)?.n_clips || settings?.n_clips || 5);
  const [brief, setBrief] = useState(project(pid)?.brief ?? "");

  async function go() {
    try {
      await post(`/api/project/${pid}/reanalyze`, { n_clips: n, brief });
      onClose();
      refresh();
    } catch {}
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Cari ulang momen</DialogTitle>
        <DialogDescription>
          Daftar clip sekarang akan diganti dengan hasil pencarian baru. Transkrip dipakai ulang, jadi cepat.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="re_brief">Referensi & instruksi (opsional)</Label>
        <BriefField value={brief} onChange={setBrief} hasKey={Boolean(settings?.has_key)} id="re_brief" />
      </div>
      <div className="flex items-center gap-3">
        <Label htmlFor="re_n">Berapa clip yang dicari?</Label>
        <Input
          id="re_n"
          type="number"
          min={1}
          max={20}
          value={n}
          onChange={(e) => setN(Number(e.target.value) || 1)}
          className="w-20"
        />
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Batal
        </Button>
        <Button onClick={go}>Cari ulang</Button>
      </DialogFooter>
    </>
  );
}
