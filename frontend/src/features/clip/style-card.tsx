"use client";

import {
  CheckIcon,
  ChevronRightIcon,
  InfoIcon,
  Loader2Icon,
  SaveIcon,
  SlidersHorizontalIcon,
  SparklesIcon,
  WandSparklesIcon,
} from "lucide-react";
import { useState } from "react";

import { localAIReady, useNero } from "@/components/nero/store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import { SaveStyleDialog, StyleThumb } from "./style-parts";
import { useStyles } from "./style-store";
import { useStore } from "./store";
import type { StyleEntry } from "./types";

/** Langkah 2: gaya aktif, tiru gaya dari clip, dan galeri gaya (Gaya saya + preset). */
export function StyleCard() {
  const { settings } = useStore();
  const { library, activeName, find, setEditorOpen, setRefOpen, job } = useStyles();
  const [tab, setTab] = useState<"mine" | "preset" | null>(null);
  const [saving, setSaving] = useState(false);

  if (!settings) return null;
  const mine = library?.styles ?? [];
  const presets = library?.presets ?? [];
  const shown = tab ?? (mine.length ? "mine" : "preset");
  const items = shown === "mine" ? mine : presets;
  const active = find(settings.active_style_id);
  const unsaved = !active || library?.active_modified;
  const running = job?.status === "proses";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2">
        <CardTitle className="text-base">2. Gaya video</CardTitle>
        <div className="flex-1" />
        <AIStatus />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex gap-3.5 rounded-xl border p-3">
          <StyleThumb id="current" k={library?.current_thumb} className="w-[5.5rem] flex-none" />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Gaya aktif</p>
            <p className="leading-tight font-bold break-words">{activeName}</p>
            <p className="line-clamp-3 text-xs text-muted-foreground">
              {active?.summary ||
                (active ? "Dipakai untuk semua video, kecuali video yang diberi gaya sendiri." : "Gaya hasil pengaturan Anda sendiri.")}
            </p>
            <div className="mt-auto flex flex-wrap gap-2 pt-1.5">
              <Button size="sm" variant="outline" onClick={() => setEditorOpen(true)}>
                <SlidersHorizontalIcon /> Atur detail
              </Button>
              {unsaved && (
                <Button size="sm" variant="ghost" onClick={() => setSaving(true)}>
                  <SaveIcon /> Simpan
                </Button>
              )}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setRefOpen(true)}
          className="group flex items-center gap-3 rounded-xl border border-dashed p-3 text-left transition-colors hover:border-foreground/40 hover:bg-muted/50"
        >
          <span className="grid size-9 flex-none place-items-center rounded-lg bg-foreground text-background">
            {running ? <Loader2Icon className="size-4 animate-spin" /> : <WandSparklesIcon className="size-4" />}
          </span>
          <span className="min-w-0 flex-1">
            <b className="text-sm">Tiru gaya dari clip</b>
            <span className="block truncate text-xs text-muted-foreground">
              {running
                ? `${Math.round((job?.progress ?? 0) * 100)}% · ${job?.stage}`
                : "Tempel link TikTok / Reels / Shorts, AI membaca gaya editingnya"}
            </span>
          </span>
          <ChevronRightIcon className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        </button>

        <div className="flex flex-col gap-2.5">
          <div className="flex w-fit gap-0.5 rounded-lg bg-muted p-0.5 text-xs" role="tablist" aria-label="Daftar gaya">
            {(
              [
                ["mine", `Gaya saya (${mine.length})`],
                ["preset", `Siap pakai (${presets.length})`],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={shown === k}
                onClick={() => setTab(k)}
                className={cn(
                  "rounded-md px-2.5 py-1 font-medium text-muted-foreground transition-colors",
                  shown === k && "bg-background text-foreground shadow-sm",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {library === null ? (
            <p className="py-6 text-center text-xs text-muted-foreground">Memuat gaya...</p>
          ) : items.length === 0 ? (
            <p className="rounded-lg bg-muted/60 px-3 py-5 text-center text-xs text-muted-foreground">
              Belum ada gaya tersimpan. Tiru gaya dari clip, atau tekan <b className="text-foreground">Simpan</b> pada
              gaya aktif. Semua gaya yang pernah dibaca akan muncul di sini.
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 lg:grid-cols-3">
              {items.map((s) => (
                <StyleTile key={s.id} s={s} active={s.id === library.active_id} />
              ))}
            </div>
          )}
        </div>
      </CardContent>
      <SaveStyleDialog open={saving} onClose={() => setSaving(false)} />
    </Card>
  );
}

function StyleTile({ s, active }: { s: StyleEntry; active: boolean }) {
  const { apply, setDetail } = useStyles();
  const fromRef = s.source?.kind === "referensi";
  return (
    <div className="group relative min-w-0">
      <button
        type="button"
        onClick={() => (active ? setDetail(s) : apply(s.id))}
        title={active ? `${s.name} (sedang dipakai)` : `Pakai gaya "${s.name}"`}
        className={cn(
          "block w-full overflow-hidden rounded-lg ring-1 ring-foreground/10 transition hover:ring-foreground/50",
          active && "ring-2 ring-foreground hover:ring-foreground",
        )}
      >
        <StyleThumb id={s.id} k={s.thumb} className="w-full rounded-none" />
      </button>
      {active && (
        <span className="pointer-events-none absolute top-1.5 left-1.5 grid size-5 place-items-center rounded-full bg-foreground text-background">
          <CheckIcon className="size-3" />
        </span>
      )}
      <button
        type="button"
        onClick={() => setDetail(s)}
        aria-label={`Detail gaya ${s.name}`}
        title="Detail, ganti nama, hapus"
        className="absolute top-1.5 right-1.5 grid size-6 place-items-center rounded-md bg-black/65 text-white transition-opacity focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
      >
        <InfoIcon className="size-3.5" />
      </button>
      <p className="mt-1 truncate text-xs font-medium" title={s.name}>
        {s.name}
      </p>
      {fromRef && (
        <p className="flex items-center gap-1 truncate text-[10px] text-muted-foreground">
          {s.ai_model && <SparklesIcon className="size-2.5 flex-none" />}
          {s.ai_model ? "Dibaca AI" : "Dibaca tanpa AI"}
        </p>
      )}
    </div>
  );
}

/** Tanda kecil: AI lokal siap / belum. Klik untuk membuka pengaturannya. */
function AIStatus() {
  const { localAI, setSettingsOpen } = useNero();
  if (!localAI) return null;
  const ready = localAIReady(localAI);
  if (!localAI.on) return null;
  return (
    <button
      type="button"
      onClick={() => setSettingsOpen(true)}
      title={ready ? `Model: ${localAI.chosen}` : "Klik untuk menyiapkan AI lokal gratis"}
      className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
    >
      <span className={cn("size-1.5 rounded-full", ready ? "bg-ok" : "bg-warn")} />
      {ready ? "AI lokal siap" : "Siapkan AI lokal"}
    </button>
  );
}
