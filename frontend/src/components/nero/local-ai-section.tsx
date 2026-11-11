"use client";

import {
  CheckIcon,
  DownloadIcon,
  ExternalLinkIcon,
  HardDriveIcon,
  Loader2Icon,
  RefreshCwIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { SimpleSelect, type Option } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { localAIReady, useNero } from "./store";

/** Pilihan AI untuk meniru gaya: Gemini (online) atau AI lokal (offline). */
export function ProviderPicker({
  value,
  onChange,
}: {
  value: "lokal" | "gemini";
  onChange: (v: "lokal" | "gemini") => void;
}) {
  const items = [
    {
      v: "gemini" as const,
      icon: SparklesIcon,
      title: "Google Gemini",
      badge: "Online · paling pintar",
      text: "Menonton videonya langsung, termasuk animasi subtitle & zoom. Gratis dengan API key Google.",
    },
    {
      v: "lokal" as const,
      icon: HardDriveIcon,
      title: "AI lokal (Ollama)",
      badge: "Offline",
      text: "Berjalan di laptop ini, video tidak keluar. Lebih lambat & kurang teliti.",
    },
  ];
  return (
    <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="AI untuk meniru gaya">
      {items.map((it) => (
        <button
          key={it.v}
          type="button"
          role="radio"
          aria-checked={value === it.v}
          onClick={() => onChange(it.v)}
          className={cn(
            "flex flex-col gap-1 rounded-xl border p-3 text-left transition-colors hover:bg-muted/60",
            value === it.v && "border-foreground bg-muted/60",
          )}
        >
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            <it.icon className="size-4" /> {it.title}
          </span>
          <span className="text-[11px] font-medium text-muted-foreground">{it.badge}</span>
          <span className="text-xs text-muted-foreground">{it.text}</span>
        </button>
      ))}
    </div>
  );
}

/** API key & model Google Gemini (paket gratis). Kuncinya tidak pernah dikirim balik ke halaman. */
export function GeminiSection({
  keyValue,
  setKey,
  model,
  setModel,
  hasKey,
}: {
  keyValue: string;
  setKey: (v: string) => void;
  model: string;
  setModel: (v: string) => void;
  hasKey: boolean;
}) {
  const { localAI, loadSettings, loadLocalAI } = useNero();
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; error: string } | null>(null);
  const keyPage = localAI?.gemini.key_page ?? "https://aistudio.google.com/api-keys";

  async function check() {
    setChecking(true);
    setResult(null);
    try {
      setResult(await post<{ ok: boolean; error: string }>("/api/gemini/check", { key: keyValue.trim(), model: model.trim() }));
    } catch {
    } finally {
      setChecking(false);
    }
  }

  async function clear() {
    try {
      await post("/api/settings", { clear_gemini_key: true });
      await Promise.all([loadSettings(), loadLocalAI()]);
      setResult(null);
      toast.success("API key Gemini dihapus");
    } catch {}
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border p-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="s_gemini_key" className="text-xs font-normal text-muted-foreground">
          API key Gemini
        </Label>
        <div className="flex gap-2">
          <Input
            id="s_gemini_key"
            type="password"
            autoComplete="off"
            value={keyValue}
            onChange={(e) => setKey(e.target.value)}
            placeholder={hasKey ? "Tersimpan. Kosongkan untuk tetap memakai yang lama." : "Tempel API key di sini"}
            className="min-w-0 flex-1"
          />
          <Button variant="outline" onClick={check} disabled={checking || (!hasKey && !keyValue.trim())}>
            {checking ? <Loader2Icon className="animate-spin" /> : <CheckIcon />} Cek
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {result ? (
            <span className={result.ok ? "text-ok" : "text-destructive"}>
              {result.ok ? "✓ API key berfungsi." : result.error}
            </span>
          ) : (
            <span className={hasKey ? "text-ok" : "text-muted-foreground"}>
              {hasKey ? "✓ API key tersimpan." : "Belum ada API key."}
            </span>
          )}
          <a
            href={keyPage}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-4"
          >
            Buat API key gratis <ExternalLinkIcon className="size-3" />
          </a>
          {hasKey && (
            <button type="button" onClick={clear} className="text-muted-foreground underline underline-offset-4">
              Hapus
            </button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="s_gemini_model" className="text-xs font-normal text-muted-foreground">
          Model Gemini
        </Label>
        <Input id="s_gemini_model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gemini-3.8-flash" />
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Klik <b className="text-foreground">Buat API key gratis</b>, masuk dengan akun Google, tekan{" "}
        <b className="text-foreground">Create API key</b>, lalu salin ke sini. Di paket gratis ada batas pemakaian
        harian, dan clip yang dikirim boleh dipakai Google untuk meningkatkan produknya, jadi jangan pakai untuk video
        pribadi. Bila Gemini gagal (kuota habis / tanpa internet), Nero otomatis memakai AI lokal.
      </p>
    </div>
  );
}

/** Pengaturan AI lokal gratis (di dialog Pengaturan Nero): status Ollama, pilihan model, unduh model. */
export function LocalAISection({
  url,
  setUrl,
  model,
  setModel,
  serverKey,
  setServerKey,
  hasServerKey,
  title,
}: {
  url: string;
  setUrl: (v: string) => void;
  /** "auto" = pilih otomatis */
  model: string;
  setModel: (v: string) => void;
  /** kunci untuk server bergaya OpenAI di internet (OpenRouter, Groq) */
  serverKey: string;
  setServerKey: (v: string) => void;
  hasServerKey: boolean;
  title: string;
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
  // server di internet (bukan komputer ini): butuh API key
  const remote = !/^(https?:\/\/)?(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(url.trim() || "127.0.0.1");

  return (
    <div className="flex flex-col gap-3 rounded-xl border p-3">
      <p className="text-xs font-medium">{title}</p>
      <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs">
        {ai === null ? (
          <span className="text-muted-foreground">Memeriksa AI lokal...</span>
        ) : ai.status.ok ? (
          <span className={cn(localAIReady(ai) ? "text-ok" : "text-warn")}>
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
      {(remote || hasServerKey) && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="s_ai_key" className="text-xs font-normal text-muted-foreground">
            API key server (mis. OpenRouter atau Groq)
          </Label>
          <Input
            id="s_ai_key"
            type="password"
            autoComplete="off"
            value={serverKey}
            onChange={(e) => setServerKey(e.target.value)}
            placeholder={hasServerKey ? "Tersimpan. Kosongkan untuk tetap memakai yang lama." : "Tempel API key server"}
          />
          <span className="text-[11px] text-muted-foreground">
            Server di internet menerima gambar dari clip Anda. Isi alamat seperti https://openrouter.ai/api/v1.
          </span>
        </div>
      )}
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
