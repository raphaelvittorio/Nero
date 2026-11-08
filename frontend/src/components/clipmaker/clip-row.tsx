"use client";

import {
  ArrowRightIcon,
  CaptionsIcon,
  ClipboardCopyIcon,
  DownloadIcon,
  FolderOpenIcon,
  LightbulbIcon,
  LinkIcon,
  MapPinIcon,
  PinIcon,
  PlayIcon,
  RotateCwIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { api, clipBusy, fmt, outUrl, parseT, post } from "@/lib/api";
import type { Clip, Project } from "@/lib/types";
import { cn } from "@/lib/utils";

import { CommitInput } from "./fields";
import { useStore } from "./store";

const REF_BADGE = {
  timeline: { icon: <PinIcon />, label: "Timeline Anda" },
  link: { icon: <LinkIcon />, label: "Sama dengan clip referensi" },
  titik: { icon: <MapPinIcon />, label: "Titik riset Anda" },
} as const;

/** Koreksi kata subtitle (salah dengar nama, istilah, bahasa gaul). Waktu tiap kata dipertahankan. */
function SubtitleEditor({ p, c, onClose }: { p: Project; c: Clip; onClose: () => void }) {
  const { refresh } = useStore();
  const [text, setText] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    api<{ text: string }>(`/api/project/${p.id}/clip/${c.id}/subtitle`)
      .then((r) => alive && setText(r.text))
      .catch(() => alive && onClose());
    return () => {
      alive = false;
    };
  }, [p.id, c.id, onClose]);

  async function save() {
    if (text === null) return;
    setSaving(true);
    try {
      const r = await post<{ ok: boolean; changed: number }>(`/api/project/${p.id}/clip/${c.id}/subtitle`, { text });
      if (!r.changed) toast("Tidak ada kata yang berubah");
      else
        toast.success(
          `${r.changed} kata dikoreksi` + (c.render_status === "selesai" ? ". Render ulang clip ini untuk menerapkannya." : ""),
        );
      onClose();
      refresh();
    } catch {
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-8">Edit subtitle</DialogTitle>
        <DialogDescription>
          Perbaiki kata yang salah dengar (nama orang, istilah, bahasa gaul). Waktu tiap kata tetap dipakai, jadi
          sebaiknya ganti kata saja, jangan menambah atau menghapus banyak kata. Koreksi ikut tersimpan di transkrip.
        </DialogDescription>
      </DialogHeader>
      {text === null ? (
        <p className="py-8 text-center text-muted-foreground">Memuat subtitle...</p>
      ) : (
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="min-h-48 text-[15px] leading-relaxed"
          spellCheck={false}
          autoFocus
          aria-label="Teks subtitle"
        />
      )}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Batal
        </Button>
        <Button onClick={save} disabled={text === null || saving}>
          Simpan
        </Button>
      </DialogFooter>
    </>
  );
}

function scoreClass(s: number) {
  return s >= 80 ? "text-ok" : s >= 65 ? "text-primary" : "text-muted-foreground";
}

export function ClipRow({ p, c }: { p: Project; c: Clip }) {
  const { refresh, confirm, setPlayer } = useStore();
  const [textOpen, setTextOpen] = useState(false);
  const [subOpen, setSubOpen] = useState(false);
  // tetap sama antar-render, supaya editor tidak memuat ulang teks saat status diperbarui berkala
  const closeSub = useCallback(() => setSubOpen(false), []);
  const hasSource = Boolean(p.source);
  const busy = clipBusy(c);
  const rs = c.render_status;
  const done = rs === "selesai" && c.file;

  async function update(patch: Partial<Clip>) {
    try {
      await post(`/api/project/${p.id}/clip`, { id: c.id, ...patch });
    } catch {}
    refresh();
  }

  async function renderOne() {
    try {
      await post(`/api/project/${p.id}/render`, { ids: [c.id] });
      toast.success("Masuk antrian render");
    } catch {}
    refresh();
  }

  async function cancelRender() {
    try {
      const r = await post(`/api/project/${p.id}/cancel`, { cid: c.id });
      toast(r.count ? "Dibatalkan" : "Tidak ada yang perlu dibatalkan");
    } catch {}
    refresh();
  }

  async function remove() {
    if (!(await confirm({ title: "Hapus clip ini dari daftar?", action: "Hapus", destructive: true }))) return;
    try {
      await api(`/api/project/${p.id}/clip/${c.id}`, { method: "DELETE" });
    } catch {}
    refresh();
  }

  function copyCaption() {
    const t = (c.caption || c.title || "") + "\n\n" + (c.hashtags ?? []).join(" ");
    navigator.clipboard.writeText(t).then(
      () => toast.success("Caption + hashtag disalin"),
      () => window.prompt("Salin caption:", t),
    );
  }

  const nudge = (key: "start" | "end", d: number) =>
    update({ [key]: Math.max(0, +(c[key] + d).toFixed(2)) });

  const file = done ? outUrl(c) : "";
  return (
    <div className="grid grid-cols-[auto_auto_1fr] gap-x-3.5 gap-y-3 px-4 py-3.5 sm:px-5 lg:grid-cols-[auto_auto_1fr_auto]">
      <Dialog open={subOpen} onOpenChange={setSubOpen}>
        <DialogContent className="sm:max-w-xl">
          {subOpen && <SubtitleEditor p={p} c={c} onClose={closeSub} />}
        </DialogContent>
      </Dialog>
      <Checkbox
        className="mt-1"
        checked={c.selected}
        onCheckedChange={(v) => update({ selected: v === true })}
        aria-label="Pilih clip untuk dirender"
      />
      <div
        className={cn(
          "grid size-14 place-content-center rounded-xl bg-muted text-center text-xl leading-none font-extrabold",
          scoreClass(c.score ?? 0),
        )}
        title="Perkiraan potensi viral"
      >
        {c.score || "–"}
        <small className="mt-1 block text-[10px] font-semibold text-muted-foreground">skor</small>
      </div>

      <div className="min-w-0">
        <CommitInput
          value={c.title}
          onCommit={(v) => update({ title: v })}
          title="Judul/hook (tampil di atas video)"
          className="-ml-2 border-transparent bg-transparent! px-2 text-[15px] font-bold hover:border-border"
        />
        <div className="my-1.5 flex flex-wrap items-center gap-2">
          <CommitInput
            value={fmt(c.start)}
            onCommit={(v) => update({ start: parseT(v) })}
            title="Mulai"
            aria-label="Waktu mulai"
            className="h-7 w-20 tabular-nums"
          />
          <ArrowRightIcon className="size-3.5 text-muted-foreground" />
          <CommitInput
            value={fmt(c.end)}
            onCommit={(v) => update({ end: parseT(v) })}
            title="Selesai"
            aria-label="Waktu selesai"
            className="h-7 w-20 tabular-nums"
          />
          <span className="text-xs text-muted-foreground">{(c.end - c.start).toFixed(0)} dtk</span>
          <Button variant="ghost" size="xs" onClick={() => nudge("start", -1)} title="Mulai 1 dtk lebih awal">
            ⇤ -1
          </Button>
          <Button variant="ghost" size="xs" onClick={() => nudge("end", 1)} title="Selesai 1 dtk lebih lama">
            +1 ⇥
          </Button>
          <Button variant="outline" size="xs" onClick={() => setSubOpen(true)} title="Koreksi kata yang salah dengar">
            <CaptionsIcon /> Subtitle
          </Button>
          {hasSource && (
            <Button
              variant="outline"
              size="xs"
              onClick={() =>
                setPlayer({
                  mode: "preview",
                  src: `/media/${p.id}/${encodeURIComponent(p.source!)}`,
                  start: c.start,
                  end: c.end,
                  title: c.title,
                })
              }
            >
              <PlayIcon /> Pratinjau
            </Button>
          )}
        </div>
        {(c.ref || c.reason) && (
          <div className="mb-1.5 flex flex-wrap gap-1.5">
            {c.ref && (
              <Badge variant="outline" className="text-primary">
                {REF_BADGE[c.ref].icon} {REF_BADGE[c.ref].label}
              </Badge>
            )}
            {c.reason && (
              <Badge variant="secondary" className="h-auto whitespace-normal text-muted-foreground">
                <LightbulbIcon /> {c.reason}
              </Badge>
            )}
          </div>
        )}
        <p
          onClick={() => setTextOpen((v) => !v)}
          className={cn("cursor-pointer text-[13px] text-muted-foreground", !textOpen && "line-clamp-2")}
        >
          {c.text}
        </p>
      </div>

      <div className="col-span-3 flex min-w-44 flex-wrap items-center justify-end gap-2 lg:col-span-1 lg:flex-col lg:items-end">
        {rs === "antri" && <Badge variant="outline" className="text-info">Antri render</Badge>}
        {rs === "proses" && (
          <div className="flex w-40 flex-col items-end gap-1.5">
            <Badge variant="outline" className="text-info">
              Render {Math.round((c.render_progress ?? 0) * 100)}%
            </Badge>
            <Progress value={(c.render_progress ?? 0) * 100} className="w-full" />
          </div>
        )}
        {rs === "gagal" && (
          <Badge variant="destructive" title={c.error}>
            Gagal render
          </Badge>
        )}
        {c.subs_changed && rs === "selesai" && (
          <Badge variant="outline" className="text-warn" title="Subtitle dikoreksi setelah render terakhir">
            Subtitle diubah, render ulang
          </Badge>
        )}
        {busy && (
          <Button variant="ghost" size="sm" onClick={cancelRender}>
            <XIcon /> Batal render
          </Button>
        )}

        {done ? (
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setPlayer({ mode: "result", src: file, title: c.title })}
              title="Putar hasil"
              className="overflow-hidden rounded-lg bg-black"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${file.replace(/\.mp4$/, ".jpg")}?v=${c.rendered_at ?? 0}`}
                alt={`Thumbnail ${c.title}`}
                className="h-24 w-[54px] object-cover"
              />
            </button>
            <div className="flex flex-col gap-1.5">
              <a href={`${file}?dl=1`} className={buttonVariants({ size: "sm" })}>
                <DownloadIcon /> Unduh
              </a>
              <Button variant="outline" size="sm" onClick={copyCaption}>
                <ClipboardCopyIcon /> Caption
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => post("/api/open-folder", { path: c.file }).catch(() => {})}
                title="Buka folder hasil"
              >
                <FolderOpenIcon /> Folder
              </Button>
            </div>
          </div>
        ) : (
          hasSource &&
          !busy && (
            <Button variant="outline" size="sm" onClick={renderOne}>
              <PlayIcon /> Render
            </Button>
          )
        )}
        {hasSource && rs === "selesai" && (
          <Button variant="ghost" size="sm" onClick={renderOne}>
            <RotateCwIcon /> Render ulang
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-destructive"
          onClick={remove}
          title="Hapus clip"
          aria-label="Hapus clip"
        >
          <XIcon />
        </Button>
      </div>
    </div>
  );
}
