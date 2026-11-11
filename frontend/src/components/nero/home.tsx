"use client";

import { ArrowRightIcon, CpuIcon, LayersIcon, PlusIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";

import { FEATURES, type Feature } from "@/features";
import { cn } from "@/lib/utils";

import { useNero } from "./store";

/** Beranda: ringkasan semua fitur. */
export function Home() {
  const { summaries, settings, setSettingsOpen } = useNero();
  const busy = Object.values(summaries).reduce((n, f) => n + f.busy, 0);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:py-12">
      <section>
        <h1 className="text-3xl font-extrabold tracking-tight text-balance sm:text-4xl">Selamat datang di Nero</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground text-pretty">
          Kumpulan alat untuk menghasilkan uang dari internet. Semua berjalan di komputer Anda sendiri.
        </p>
      </section>

      <section className="mt-8 grid gap-3 sm:grid-cols-3" aria-label="Ringkasan">
        <Tile icon={LayersIcon} label="Fitur aktif" value={String(FEATURES.length)} />
        <Tile
          icon={CpuIcon}
          label="Sedang berjalan"
          value={busy ? `${busy} tugas` : "Tidak ada"}
          live={busy > 0}
        />
        <Tile
          icon={SparklesIcon}
          label="Mode AI"
          value={settings ? (settings.has_key ? "Claude aktif" : "Lokal (gratis)") : "..."}
          action={
            settings && !settings.has_key ? (
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className="text-xs font-medium underline underline-offset-4 hover:text-foreground"
              >
                Tambah API key
              </button>
            ) : null
          }
        />
      </section>

      <h2 className="mt-10 mb-4 text-sm font-semibold tracking-wider text-muted-foreground uppercase">Fitur</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {FEATURES.map((f) => (
          <FeatureCard key={f.id} f={f} />
        ))}
        <div className="flex flex-col items-start rounded-xl border border-dashed p-5 text-muted-foreground">
          <span className="grid size-10 place-items-center rounded-lg border border-dashed">
            <PlusIcon className="size-5" />
          </span>
          <h3 className="mt-4 font-semibold text-foreground">Fitur berikutnya</h3>
          <p className="mt-1 text-sm">Alat baru untuk menghasilkan uang akan muncul di sini.</p>
        </div>
      </div>
    </main>
  );
}

function Tile({
  icon: Icon,
  label,
  value,
  live,
  action,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  live?: boolean;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-card px-4 py-3.5 ring-1 ring-foreground/10">
      <Icon className="size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="flex items-center gap-2 font-semibold whitespace-nowrap">
          {live && <span className="size-1.5 animate-[pulse-dot_1.2s_ease-in-out_infinite] rounded-full bg-foreground" />}
          {value}
        </p>
        {action && <div className="mt-0.5 text-muted-foreground">{action}</div>}
      </div>
    </div>
  );
}

function FeatureCard({ f }: { f: Feature }) {
  const s = useNero().summaries[f.id];
  const Icon = f.icon;
  return (
    <Link
      href={f.href}
      className="group flex flex-col rounded-xl bg-card p-5 ring-1 ring-foreground/10 transition-shadow hover:ring-foreground/35 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-10 place-items-center rounded-lg bg-foreground text-background">
          <Icon className="size-5" />
        </span>
        {s && s.busy > 0 && (
          <span className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium">
            <span className="size-1.5 animate-[pulse-dot_1.2s_ease-in-out_infinite] rounded-full bg-foreground" />
            {s.busy} berjalan
          </span>
        )}
      </div>
      <h3 className="mt-4 text-lg font-bold">{f.name}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{f.description}</p>
      {s && s.stats.length > 0 && (
        <dl className={cn("mt-5 grid gap-2 border-t pt-4", s.stats.length >= 3 ? "grid-cols-3" : "grid-cols-2")}>
          {s.stats.map((st) => (
            <div key={st.label} className="min-w-0">
              <dt className="truncate text-[11px] text-muted-foreground">{st.label}</dt>
              <dd className="text-xl font-bold tabular-nums">{st.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold">
        Buka {f.name}
        <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}
