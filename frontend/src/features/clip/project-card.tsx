"use client";

import {
  ClapperboardIcon,
  EraserIcon,
  FileTextIcon,
  PlayIcon,
  PlusIcon,
  RotateCwIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api, post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { API, fmt, isBusy, mediaUrl, projectRunning, sizeText } from "./api";
import { ClipRow } from "./clip-row";
import { useStore } from "./store";
import type { Project } from "./types";

const DOT: Record<Project["status"], string> = {
  antri: "bg-muted-foreground",
  proses: "bg-info animate-[pulse-dot_1s_infinite]",
  siap: "bg-ok",
  gagal: "bg-destructive",
};

export function ProjectCard({ p, onReanalyze }: { p: Project; onReanalyze: (pid: string) => void }) {
  const { refresh, confirm, setTranscriptPid } = useStore();
  const running = projectRunning(p);
  const clips = p.clips ?? [];
  const hasSource = Boolean(p.source);
  const src = mediaUrl(p);

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch {}
    refresh();
  }

  const cancel = () =>
    act(async () => {
      const r = await post(`${API}/project/${p.id}/cancel`);
      toast(r.count ? "Dibatalkan" : "Tidak ada yang perlu dibatalkan");
    });

  const remove = async () => {
    const ok = await confirm({
      title: "Hapus proyek ini?",
      description: "Video hasil di folder output tetap aman.",
      action: "Hapus",
      destructive: true,
    });
    if (ok) act(() => api(`${API}/project/${p.id}`, { method: "DELETE" }));
  };

  const dropSource = async () => {
    const ok = await confirm({
      title: "Hapus video sumber untuk menghemat disk?",
      description:
        "Hasil render di folder output tetap aman, tetapi clip proyek ini tidak bisa dirender lagi.",
      action: "Hapus video sumber",
      destructive: true,
    });
    if (ok)
      act(async () => {
        await post(`${API}/project/${p.id}/drop-source`);
        toast.success("Video sumber dihapus");
      });
  };

  const renderSelected = () =>
    act(async () => {
      const r = await post(`${API}/project/${p.id}/render`);
      toast.success(`${r.count} clip masuk antrian render`);
    });

  const addManual = () =>
    act(async () => {
      await post(`${API}/project/${p.id}/clip`, {
        start: 0,
        end: Math.min(30, p.duration || 30),
        title: "Clip baru",
      });
      toast.success("Clip ditambahkan, atur waktu mulai & selesai");
    });

  return (
    <article className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
      <div className="flex flex-wrap items-center gap-4 border-b px-4 py-4 sm:flex-nowrap sm:px-5">
        {src ? (
          <video
            src={`${src}#t=5`}
            muted
            preload="metadata"
            className="aspect-video w-36 flex-none rounded-lg bg-black object-cover"
          />
        ) : (
          <div className="grid aspect-video w-36 flex-none place-items-center rounded-lg bg-muted text-muted-foreground">
            <ClapperboardIcon className="size-5" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="mb-0.5 font-bold break-words">{p.title}</p>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className={cn("size-2 flex-none rounded-full", DOT[p.status])} />
            <span>{p.stage}</span>
            {p.used_ai && <Badge variant="secondary">AI</Badge>}
            {p.brief && (
              <Badge variant="outline" className="text-primary" title={p.brief}>
                Pakai referensi
              </Badge>
            )}
          </div>
          {running && <Progress value={(p.progress ?? 0) * 100} className="mt-2" />}
          {p.error && <p className="mt-1.5 text-sm break-words text-destructive">⚠ {p.error}</p>}
          {p.warning && <p className="mt-1.5 text-sm text-warn">{p.warning}</p>}
        </div>
        <div className="flex items-center gap-2">
          {p.status === "gagal" && !p.source_removed && (
            <Button variant="outline" size="sm" onClick={() => act(() => post(`${API}/project/${p.id}/retry`))}>
              <RotateCwIcon /> Ulangi
            </Button>
          )}
          {running && (
            <Button variant="outline" size="sm" onClick={cancel} title="Hentikan proses">
              <XIcon /> Batal
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-destructive"
            onClick={remove}
            title="Hapus proyek"
            aria-label="Hapus proyek"
          >
            <Trash2Icon />
          </Button>
        </div>
      </div>

      {p.status === "siap" && (
        <>
          <div className="flex flex-wrap items-center gap-2 border-b bg-muted/60 px-4 py-3 sm:px-5">
            {hasSource ? (
              <>
                <Button size="sm" onClick={renderSelected}>
                  <PlayIcon /> Render {clips.filter((c) => c.selected).length} clip terpilih
                </Button>
                <Button variant="outline" size="sm" onClick={addManual}>
                  <PlusIcon /> Clip manual
                </Button>
                <Button variant="outline" size="sm" onClick={() => setTranscriptPid(p.id)}>
                  <FileTextIcon /> Transkrip
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onReanalyze(p.id)}
                  title="Cari ulang momen, bisa dengan timeline riset / link referensi / instruksi"
                >
                  <RotateCwIcon /> Cari ulang + referensi
                </Button>
              </>
            ) : (
              <Badge variant="secondary" className="h-auto whitespace-normal">
                Video sumber sudah dihapus. Hasil render di folder output tetap aman.
              </Badge>
            )}
            <div className="flex-1" />
            <span className="text-xs text-muted-foreground">
              {p.duration ? `Durasi ${fmt(p.duration)}` : ""}
              {p.size_mb ? ` · ${sizeText(p)}` : ""}
            </span>
            {hasSource && !isBusy(p) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={dropSource}
                title="Hapus video asli & audio untuk menghemat disk"
              >
                <EraserIcon /> Hapus video sumber
              </Button>
            )}
          </div>
          {clips.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              Tidak ada momen ditemukan. Coba &ldquo;Clip manual&rdquo; atau &ldquo;Transkrip&rdquo;.
            </p>
          ) : (
            <div className="divide-y">
              {clips.map((c) => (
                <ClipRow key={c.id} p={p} c={c} />
              ))}
            </div>
          )}
        </>
      )}
    </article>
  );
}
