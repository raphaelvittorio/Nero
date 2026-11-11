"use client";

import { CheckIcon, DownloadIcon, ExternalLinkIcon, Loader2Icon, RefreshCwIcon, XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { SimpleSelect, type Option } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { localAIReady, useNero } from "./store";

/** Pengaturan AI lokal gratis (di dialog Pengaturan Nero): status Ollama, pilihan model, unduh model. */
export function LocalAISection({
  url,
  setUrl,
  model,
  setModel,
  on,
  setOn,
}: {
  url: string;
  setUrl: (v: string) => void;
  /** "auto" = pilih otomatis */
  model: string;
  setModel: (v: string) => void;
  on: boolean;
  setOn: (v: boolean) => void;
}) {
  const { localAI: ai, loadLocalAI } = useNero();
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    loadLocalAI();
  }, [loadLocalAI]);

  async function check() {
    setChecking(true);
    // alamat yang baru diketik dicoba dengan menyimpannya dulu
    if (ai && url.trim() && url.trim() !== ai.url) {
      await post("/api/settings", { local_ai_url: url.trim() }).catch(() => {});
    }
    await loadLocalAI();
    setChecking(false);
  }

  async function pull(name: string) {
    try {
      await post("/api/local-ai/pull", { model: name });
      toast(`Mulai mengunduh ${name}. Jendela ini boleh ditutup.`);
      loadLocalAI();
    } catch {}
  }

  const installed = ai?.status.models ?? [];
  const vision = installed.filter((m) => m.vision);
  const models: Option<string>[] = [
    ["auto", ai?.chosen ? `Otomatis (sekarang: ${ai.chosen})` : "Otomatis (model terbaik yang ada)"],
    ...vision.map((m): Option<string> => [m.name, m.size_gb ? `${m.name} · ${m.size_gb} GB` : m.name]),
  ];
  if (model !== "auto" && !vision.some((m) => m.name === model)) models.push([model, `${model} (belum ada)`]);
  const pulling = ai?.pull?.status === "proses" ? ai.pull : null;

  return (
    <div className="flex flex-col gap-3 border-t pt-4">
      <div>
        <Label>AI lokal gratis untuk membaca &amp; meniru gaya editing</Label>
        <p className="mt-1 text-xs text-muted-foreground">
          Berjalan di komputer Anda lewat Ollama: gratis, tanpa API key, video tidak dikirim ke internet.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs">
        {ai === null ? (
          <span className="text-muted-foreground">Memeriksa AI lokal...</span>
        ) : ai.status.ok ? (
          <span className={cn(localAIReady(ai) || !on ? "text-ok" : "text-warn")}>
            {ai.status.kind === "ollama" ? "✓ Ollama berjalan" : "✓ Server AI lokal berjalan"} ·{" "}
            {vision.length
              ? `${vision.length} model bisa melihat gambar`
              : "belum ada model yang bisa melihat gambar, unduh salah satu di bawah"}
          </span>
        ) : (
          <span className="text-warn">{ai.status.error}</span>
        )}
        <div className="flex-1" />
        {ai && !ai.status.ok && (
          <a
            href="https://ollama.com/download"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-4"
          >
            Unduh Ollama <ExternalLinkIcon className="size-3" />
          </a>
        )}
        <Button variant="ghost" size="xs" onClick={check} disabled={checking}>
          <RefreshCwIcon className={cn(checking && "animate-spin")} /> Cek lagi
        </Button>
      </div>
      <Label className="cursor-pointer font-normal">
        <Checkbox checked={on} onCheckedChange={(v) => setOn(v === true)} />
        Pakai AI lokal saat membaca gaya dari clip referensi
      </Label>
      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label className="text-xs font-normal text-muted-foreground">Model yang dipakai</Label>
          <SimpleSelect value={model} onChange={setModel} options={models} aria-label="Model AI lokal" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="s_ai_url" className="text-xs font-normal text-muted-foreground">
            Alamat server
          </Label>
          <Input
            id="s_ai_url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://127.0.0.1:11434"
          />
        </div>
      </div>
      {ai?.status.kind !== "openai" && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs font-normal text-muted-foreground">Model yang disarankan (sekali unduh)</Label>
          <ul className="flex flex-col divide-y rounded-lg border">
            {(ai?.recommended ?? []).map((r) => {
              const have = installed.some((m) => m.name === r.name);
              const mine = pulling?.model === r.name;
              const [, desc] = r.label.split(": ");
              return (
                <li key={r.name} className="flex flex-col gap-1.5 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="min-w-0 flex-1 text-xs">
                      <span className="font-mono font-semibold">{r.name}</span>{" "}
                      <span className="text-muted-foreground">± {r.size_gb} GB</span>
                      <p className="text-muted-foreground">{desc ?? r.label}</p>
                    </div>
                    {have ? (
                      <span className="flex items-center gap-1 text-xs text-ok">
                        <CheckIcon className="size-3.5" /> Terpasang
                      </span>
                    ) : mine ? (
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => post("/api/local-ai/pull/cancel").then(loadLocalAI, () => {})}
                      >
                        <XIcon /> Batal
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={!ai?.status.ok || Boolean(pulling)}
                        onClick={() => pull(r.name)}
                      >
                        <DownloadIcon /> Unduh
                      </Button>
                    )}
                  </div>
                  {mine && pulling && (
                    <div className="flex flex-col gap-1">
                      <Progress value={pulling.progress * 100} />
                      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                        <Loader2Icon className="size-3 animate-spin" /> {pulling.stage}
                      </span>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {ai?.pull?.status === "gagal" && <p className="text-xs text-destructive">{ai.pull.error}</p>}
          {!ai?.status.ok && (
            <p className="text-xs text-muted-foreground">
              Pasang & buka Ollama dulu, lalu tekan <b className="text-foreground">Cek lagi</b>. Setelah itu model bisa
              diunduh dari sini.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
