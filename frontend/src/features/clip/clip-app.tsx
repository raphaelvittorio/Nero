"use client";

import { LinkIcon, PaletteIcon, PlayIcon, SendIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";

import { API } from "./api";
import { ClipHeader } from "./clip-header";
import { ClipSettingsDialog, PlayerDialog, ReanalyzeDialog, TranscriptDialog } from "./dialogs";
import { InputCard } from "./input-card";
import { ProjectCard } from "./project-card";
import { StyleCard } from "./style-card";
import { ReferenceDialog, StyleDetailDialog, StyleEditorDialog } from "./style-dialogs";
import { StyleProvider } from "./style-store";
import { ClipProvider, useStore } from "./store";

/** Halaman fitur Clip Maker (/clip). */
export function ClipApp() {
  return (
    <ClipProvider>
      <StyleProvider>
        <ClipHeader />
        <Main />
        <PlayerDialog />
        <TranscriptDialog />
        <ClipSettingsDialog />
        <StyleEditorDialog />
        <ReferenceDialog />
        <StyleDetailDialog />
      </StyleProvider>
    </ClipProvider>
  );
}

function Main() {
  const { settings, state, refresh } = useStore();
  const [reanalyzePid, setReanalyzePid] = useState<string | null>(null);
  const pending = state.projects.reduce(
    (n, p) => n + (p.clips ?? []).filter((c) => c.selected && c.render_status !== "selesai").length,
    0,
  );

  async function renderAll() {
    try {
      const r = await post(`${API}/render-all`);
      toast.success(`${r.count} clip masuk antrian render`);
    } catch {}
    refresh();
  }

  if (!settings) {
    return <p className="py-24 text-center text-muted-foreground">Memuat Clip Maker...</p>;
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6">
      <div className="grid items-start gap-5 lg:grid-cols-[1.35fr_1fr]">
        <InputCard />
        <StyleCard />
      </div>

      <div className="mt-8 mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-base font-bold">3. Hasil &amp; clip</h2>
        <span className="text-xs text-muted-foreground">Periksa momen, atur judul, lalu render.</span>
        <div className="flex-1" />
        {pending > 0 && (
          <Button variant="outline" size="sm" onClick={renderAll}>
            <PlayIcon /> Render semua yang dicentang ({pending})
          </Button>
        )}
      </div>

      {state.projects.length === 0 ? (
        <EmptyResults />
      ) : (
        <div className="flex flex-col gap-5">
          {state.projects.map((p) => (
            <ProjectCard key={p.id} p={p} onReanalyze={setReanalyzePid} />
          ))}
        </div>
      )}
      <ReanalyzeDialog pid={reanalyzePid} onClose={() => setReanalyzePid(null)} />
    </main>
  );
}

function EmptyResults() {
  const steps = [
    { icon: LinkIcon, title: "Tempel link video", text: "YouTube, TikTok, Instagram, atau file dari komputer." },
    { icon: PaletteIcon, title: "Pilih gaya", text: "Pakai gaya siap pakai, atau tiru gaya dari clip yang Anda suka." },
    { icon: SendIcon, title: "Render & upload", text: "Momen terbaik dipilih otomatis, tinggal centang dan render." },
  ];
  return (
    <div className="grid gap-3 rounded-xl bg-card p-5 ring-1 ring-foreground/10 sm:grid-cols-3">
      {steps.map((s, i) => (
        <div key={s.title} className="flex gap-3">
          <span className="grid size-8 flex-none place-items-center rounded-lg bg-muted text-xs font-bold">{i + 1}</span>
          <div>
            <p className="flex items-center gap-1.5 text-sm font-semibold">
              <s.icon className="size-3.5" /> {s.title}
            </p>
            <p className="text-xs text-muted-foreground">{s.text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
