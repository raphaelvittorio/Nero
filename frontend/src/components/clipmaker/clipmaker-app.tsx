"use client";

import { PlayIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";

import { AppHeader } from "./app-header";
import { PlayerDialog, ReanalyzeDialog, SettingsDialog, TranscriptDialog } from "./dialogs";
import { InputCard } from "./input-card";
import { ProjectCard } from "./project-card";
import { ClipMakerProvider, useStore } from "./store";
import { StyleCard } from "./style-card";

export function ClipMakerApp() {
  return (
    <ClipMakerProvider>
      <AppHeader />
      <Main />
      <PlayerDialog />
      <TranscriptDialog />
      <SettingsDialog />
    </ClipMakerProvider>
  );
}

function Main() {
  const { settings, state, refresh } = useStore();
  const [reanalyzePid, setReanalyzePid] = useState<string | null>(null);

  async function renderAll() {
    try {
      const r = await post("/api/render-all");
      toast.success(`${r.count} clip masuk antrian render`);
    } catch {}
    refresh();
  }

  if (!settings) {
    return <p className="py-24 text-center text-muted-foreground">Memuat ClipMaker...</p>;
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6">
      <div className="grid items-start gap-5 lg:grid-cols-[1.4fr_1fr]">
        <InputCard />
        <StyleCard />
      </div>

      <div className="mt-7 mb-4 flex items-center gap-3">
        <h2 className="text-base font-bold">3. Hasil &amp; clip</h2>
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={renderAll}>
          <PlayIcon /> Render semua yang dicentang
        </Button>
      </div>

      {state.projects.length === 0 ? (
        <div className="rounded-xl bg-card px-4 py-12 text-center text-muted-foreground ring-1 ring-foreground/10">
          Belum ada video. Tempel link di atas lalu tekan <b className="text-foreground">Proses</b>.
        </div>
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
