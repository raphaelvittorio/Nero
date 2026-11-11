"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CommitInput, SimpleSelect, type Option } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Slider } from "@/components/ui/slider";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { API } from "./api";
import { CAPTION_COLORS, FONTS, STYLE_FIELDS, describe, fontFamily, labelOf, type StyleField } from "./options";
import { thumbUrl, useStyles } from "./style-store";
import { useStore } from "./store";
import type { Style, StyleSource } from "./types";

/** Gambar contoh 9:16 sebuah gaya (dibuat server dari frame video terbaru). */
export function StyleThumb({ id, k, className }: { id: string; k?: string; className?: string }) {
  const [loaded, setLoaded] = useState<string | null>(null);
  return (
    <div className={cn("relative aspect-[9/16] overflow-hidden rounded-lg bg-muted", className)}>
      {k && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={thumbUrl(id, k)}
          alt=""
          loading="lazy"
          onLoad={() => setLoaded(k)}
          className={cn("size-full object-cover transition-opacity", loaded === k ? "opacity-100" : "opacity-0")}
        />
      )}
      {loaded !== k && <div className="absolute inset-0 animate-pulse bg-muted" />}
    </div>
  );
}

/** Satu frame contoh dari video terbaru (atau latar contoh) dengan gaya ini, diperbarui saat gaya berubah. */
export function StylePreview({ style, className }: { style: Style; className?: string }) {
  const { state } = useStore();
  const [img, setImg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const source = state.projects.find((p) => p.status === "siap" && p.source);
  const key = JSON.stringify(style);

  useEffect(() => {
    let stale = false;
    let url: string | null = null;
    const t = window.setTimeout(async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/preview-style`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ style: JSON.parse(key) }),
        });
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          throw new Error((j as { error?: string }).error || "Pratinjau gagal");
        }
        const blob = await r.blob();
        if (stale) return;
        url = URL.createObjectURL(blob);
        setImg(url);
        setError("");
      } catch (e) {
        if (!stale) setError((e as Error).message);
      } finally {
        if (!stale) setLoading(false);
      }
    }, 250);
    return () => {
      stale = true;
      window.clearTimeout(t);
      // gambar lama dilepas setelah gambar baru tampil
      if (url) window.setTimeout(() => URL.revokeObjectURL(url!), 2000);
    };
  }, [key]);

  return (
    <div className={cn("flex flex-col items-center gap-2", className)}>
      <div className="relative aspect-[9/16] w-full overflow-hidden rounded-xl border bg-black">
        {img && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={img}
            alt="Pratinjau gaya video"
            className={cn("size-full object-cover transition-opacity", loading && "opacity-60")}
          />
        )}
        {loading && !img && <div className="absolute inset-0 animate-pulse bg-muted/30" />}
      </div>
      <span className="text-center text-[11px] text-muted-foreground">
        {error ||
          (loading
            ? "Membuat pratinjau..."
            : source
              ? `Frame dari "${source.title}"`
              : "Latar contoh. Tambahkan video untuk melihat dengan video Anda.")}
      </span>
    </div>
  );
}

/** Kontrol yang tidak berlaku saat fiturnya dimatikan, mis. warna subtitle saat subtitle mati. */
const DEPENDS: Partial<Record<keyof Style, keyof Style>> = {
  title_bg: "title_on",
  title_secs: "title_on",
  title_size: "title_on",
  title_pos: "title_on",
  progress_pos: "progress_bar",
};

export function isDisabled(field: StyleField, style: Style): boolean {
  const dep = DEPENDS[field.key] ?? (field.key.startsWith("caption_") ? "captions" : undefined);
  return Boolean(dep && !style[dep]);
}

export function StyleControl({
  field,
  style,
  onChange,
}: {
  field: StyleField;
  style: Style;
  onChange: (key: keyof Style, value: unknown) => void;
}) {
  const value = style[field.key];
  const set = (v: unknown) => onChange(field.key, v);
  const off = isDisabled(field, style);
  const wide = field.type === "font" || field.type === "color";

  if (field.type === "bool") {
    return (
      <Label className={cn("cursor-pointer self-end py-1.5 font-normal", off && "pointer-events-none opacity-45")}>
        <Checkbox checked={Boolean(value)} onCheckedChange={(v) => set(v === true)} disabled={off} />
        {field.label}
      </Label>
    );
  }
  return (
    <div className={cn("flex flex-col gap-1.5", wide && "col-span-full", off && "pointer-events-none opacity-45")}>
      <Label className="flex items-baseline justify-between text-xs font-normal text-muted-foreground">
        {field.label}
        {field.type === "range" && (
          <span className="font-mono text-[11px] text-foreground tabular-nums">{describe(field.key, value)}</span>
        )}
      </Label>
      {field.type === "select" && (
        <SimpleSelect value={value as string | number} onChange={set} options={field.options} aria-label={field.label} />
      )}
      {field.type === "range" && <RangeControl field={field} value={Number(value)} onCommit={set} />}
      {field.type === "text" && (
        <CommitInput value={String(value ?? "")} onCommit={set} placeholder={field.placeholder} />
      )}
      {field.type === "color" && <ColorPicker value={String(value)} onChange={set} label={field.label} />}
      {field.type === "font" && <FontPicker value={String(value)} onChange={set} upper={style.caption_upper} />}
      {field.hint && <p className="text-[11px] text-muted-foreground">{field.hint}</p>}
    </div>
  );
}

function ColorPicker({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div className="flex flex-wrap gap-2 py-0.5">
      {Object.entries(CAPTION_COLORS).map(([name, color]) => (
        <button
          key={name}
          type="button"
          title={name}
          aria-label={`${label}: ${name}`}
          aria-pressed={value === name}
          onClick={() => onChange(name)}
          style={{ background: color }}
          className={cn(
            "size-7 rounded-full border-2 border-transparent transition-transform hover:scale-110",
            value === name && "border-foreground shadow-[inset_0_0_0_2px_var(--background)]",
          )}
        />
      ))}
    </div>
  );
}

function FontPicker({ value, onChange, upper }: { value: string; onChange: (v: string) => void; upper: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
      {FONTS.map((f) => (
        <button
          key={f.key}
          type="button"
          aria-pressed={value === f.key}
          title={`${f.label}: ${f.hint}`}
          onClick={() => onChange(f.key)}
          className={cn(
            "flex flex-col items-center gap-0.5 rounded-lg border px-1.5 py-2 transition-colors hover:bg-muted",
            value === f.key && "border-foreground bg-muted",
          )}
        >
          <span className="truncate text-lg leading-none" style={{ fontFamily: fontFamily(f.key), ...f.css }}>
            {upper ? "AA KATA" : "Aa kata"}
          </span>
          <span className="w-full truncate text-center text-[10px] text-muted-foreground">{f.label}</span>
        </button>
      ))}
    </div>
  );
}

function RangeControl({
  field,
  value,
  onCommit,
}: {
  field: Extract<StyleField, { type: "range" }>;
  value: number;
  onCommit: (v: number) => void;
}) {
  const [drag, setDrag] = useState<number | null>(null);
  const first = (v: number | readonly number[]) => (Array.isArray(v) ? v[0] : (v as number));
  return (
    <Slider
      className="py-2"
      min={field.min}
      max={field.max}
      step={field.step}
      value={[drag ?? value]}
      onValueChange={(v) => setDrag(first(v))}
      onValueCommitted={(v) => {
        setDrag(null);
        onCommit(first(v));
      }}
      aria-label={field.label}
    />
  );
}

/** Daftar pengaturan yang terbaca dari clip referensi, dengan asalnya (diukur / dinilai AI). */
export function DetectedList({
  style,
  keys,
  sources,
}: {
  style: Partial<Style>;
  keys: (keyof Style)[];
  sources?: Partial<Record<keyof Style, StyleSource>>;
}) {
  const order = STYLE_FIELDS.map((f) => f.key).filter((k) => keys.includes(k));
  if (!order.length) return <p className="text-xs text-muted-foreground">Tidak ada gaya yang bisa dibaca dari clip ini.</p>;
  return (
    <ul className="grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
      {order.map((k) => (
        <li key={k} className="flex min-w-0 items-center gap-1.5">
          {(k === "caption_color" || k === "caption_base") && (
            <span className="size-3 flex-none rounded-full border" style={{ background: CAPTION_COLORS[String(style[k])] }} />
          )}
          <span className="flex-none text-muted-foreground">{labelOf(k)}:</span>
          <span
            className="truncate font-medium"
            style={k === "caption_font" ? { fontFamily: fontFamily(String(style[k])) } : undefined}
          >
            {describe(k, style[k])}
          </span>
          {sources?.[k] && (
            <span
              className={cn(
                "ml-auto flex-none rounded px-1 py-px text-[9px] font-semibold tracking-wide uppercase",
                sources[k] === "ai" ? "bg-foreground text-background" : "border text-muted-foreground",
              )}
              title={sources[k] === "ai" ? "Dinilai AI (Gemini / AI lokal)" : "Diukur dari piksel video"}
            >
              {sources[k] === "ai" ? "AI" : "ukur"}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Simpan gaya aktif sekarang ke "Gaya saya". */
export function SaveStyleDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-sm">{open && <SaveStyleForm onClose={onClose} />}</DialogContent>
    </Dialog>
  );
}

function SaveStyleForm({ onClose }: { onClose: () => void }) {
  const { loadSettings } = useStore();
  const { loadLibrary, find } = useStyles();
  const { settings } = useStore();
  const base = find(settings?.active_style_id);
  const [name, setName] = useState(base ? `${base.name} (ubahan)` : "");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const r = await post<{ ok: boolean; style: { name: string } }>(`${API}/styles`, { name: name.trim() || "Gaya saya" });
      await Promise.all([loadSettings(), loadLibrary()]);
      toast.success(`Disimpan sebagai "${r.style.name}"`);
      onClose();
    } catch {
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Simpan ke Gaya saya</DialogTitle>
        <DialogDescription>Gaya aktif sekarang disimpan supaya bisa dipilih lagi kapan saja.</DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="style_name">Nama gaya</Label>
        <Input
          id="style_name"
          autoFocus
          maxLength={40}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && save()}
          placeholder="mis. Podcast Kuning"
        />
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Batal
        </Button>
        <Button onClick={save} disabled={busy}>
          Simpan
        </Button>
      </DialogFooter>
    </>
  );
}

/** Pilih gaya untuk satu video: ikut gaya aktif, atau salah satu gaya di pustaka. */
export function StyleSelect({
  value,
  onChange,
  className,
  size,
  ...rest
}: {
  value: string | null | undefined;
  onChange: (id: string | null) => void;
  className?: string;
  size?: "sm" | "default";
  "aria-label"?: string;
}) {
  const { library, activeName } = useStyles();
  const opts: Option<string>[] = [
    ["aktif", `Gaya aktif: ${activeName}`],
    ...(library?.styles ?? []).map((s): Option<string> => [s.id, s.name]),
    ...(library?.presets ?? []).map((s): Option<string> => [s.id, `${s.name} · siap pakai`]),
  ];
  const v = value && opts.some(([id]) => id === value) ? value : "aktif";
  return (
    <SimpleSelect
      value={v}
      onChange={(id) => onChange(id === "aktif" ? null : id)}
      options={opts}
      className={className}
      size={size}
      {...rest}
    />
  );
}
