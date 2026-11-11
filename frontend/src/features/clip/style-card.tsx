"use client";

import { ChevronRightIcon, EyeIcon, EyeOffIcon, Loader2Icon, UploadIcon, WandSparklesIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CommitInput, SimpleSelect } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { API } from "./api";
import { CAPTION_COLORS, STYLE_FIELDS, type StyleField } from "./options";
import { useStore } from "./store";
import type { Style } from "./types";

export function StyleCard() {
  const { settings, loadSettings } = useStore();
  const [style, setStyleState] = useState<Style | null>(settings?.style ?? null);
  const [open, setOpen] = useState(true);
  const [preview, setPreview] = useState(false);

  // gaya awal dari pengaturan (sekali saat pengaturan pertama kali dimuat)
  if (style === null && settings) setStyleState(settings.style);

  async function setStyle<K extends keyof Style>(key: K, value: Style[K]) {
    setStyleState((s) => (s ? { ...s, [key]: value } : s));
    try {
      await post(`${API}/settings`, { style: { [key]: value } });
      toast.success("Gaya disimpan");
    } catch {
      loadSettings().catch(() => {});
    }
  }

  if (!style) return null;
  return (
    <Card>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CardHeader>
          <CollapsibleTrigger className="flex items-center gap-1.5 text-left">
            <ChevronRightIcon
              className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-90")}
            />
            <CardTitle className="text-base">2. Gaya video</CardTitle>
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="flex flex-col gap-4 pt-3">
            <ReferenceStyle
              current={style}
              onApplied={(patch) => {
                setStyleState((s) => (s ? { ...s, ...patch } : s));
                setPreview(true);
              }}
            />
            <div className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-x-4 gap-y-3.5">
              {STYLE_FIELDS.map((f) => (
                <StyleControl key={f.key} field={f} style={style} onChange={setStyle} />
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" size="sm" onClick={() => setPreview((v) => !v)}>
                {preview ? <EyeOffIcon /> : <EyeIcon />}
                {preview ? "Tutup pratinjau" : "Pratinjau gaya"}
              </Button>
              <span className="text-xs text-muted-foreground">Lihat hasilnya di satu frame tanpa render.</span>
            </div>
            {preview && <StylePreview style={style} />}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

interface StyleFromRef {
  title: string;
  style: Partial<Style>;
  notes: string[];
  seconds: number;
}

/** Nilai gaya dalam kata-kata, memakai label yang sama dengan kontrol di bawahnya. */
function describe(key: keyof Style, v: unknown): string {
  const f = STYLE_FIELDS.find((x) => x.key === key);
  if (f?.type === "bool") return v ? "ya" : "tidak";
  if (f?.type === "select") return f.options.find(([o]) => o === v)?.[1] ?? String(v);
  if (key === "caption_pos") return `${Math.round(Number(v) * 100)}% dari atas`;
  return String(v);
}

/** Baca gaya (subtitle, judul, progress bar, tata letak) dari clip contoh, tanpa API key. */
function ReferenceStyle({ current, onApplied }: { current: Style; onApplied: (patch: Partial<Style>) => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<StyleFromRef | null>(null);
  const [preview, setPreview] = useState(false);
  const fileIn = useRef<HTMLInputElement>(null);

  async function analyze(body: { url: string } | FormData, label: string) {
    setBusy(label);
    setResult(null);
    setPreview(false);
    try {
      setResult(await post<StyleFromRef & { ok: boolean }>(`${API}/style-from-reference`, body));
    } catch {
    } finally {
      setBusy(null);
      if (fileIn.current) fileIn.current.value = "";
    }
  }

  async function apply() {
    if (!result) return;
    try {
      await post(`${API}/settings`, { style: result.style });
      onApplied(result.style);
      setResult(null);
      setUrl("");
      toast.success("Gaya dari clip referensi diterapkan");
    } catch {}
  }

  // urutan sama dengan kontrol gaya; hanya yang memang terdeteksi
  const keys = result ? STYLE_FIELDS.map((f) => f.key).filter((k) => k in result.style) : [];
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border p-3.5">
      <div>
        <p className="flex items-center gap-2 text-sm font-medium">
          <WandSparklesIcon className="size-4 text-primary" /> Tiru gaya dari clip referensi
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Tempel link TikTok / Reels / Shorts atau pilih file. Dibaca di komputer Anda, tanpa API key.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && url.trim() && !busy && analyze({ url }, url)}
          placeholder="https://www.tiktok.com/@akun/video/..."
          className="min-w-0 flex-1 basis-48"
          aria-label="Link clip referensi untuk ditiru gayanya"
        />
        <Button size="sm" className="h-8" disabled={!url.trim() || busy !== null} onClick={() => analyze({ url }, url)}>
          Baca gaya
        </Button>
        <Button variant="outline" size="sm" className="h-8" disabled={busy !== null} onClick={() => fileIn.current?.click()}>
          <UploadIcon /> File
        </Button>
        <input
          ref={fileIn}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const fd = new FormData();
            fd.append("file", f);
            analyze(fd, f.name);
          }}
        />
      </div>
      {busy && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2Icon className="size-3.5 animate-spin" /> Mengunduh & membaca gaya... (biasanya 5–30 detik)
        </p>
      )}
      {result && (
        <div className="flex flex-col gap-2 rounded-lg bg-muted/60 p-3 text-xs">
          <p className="font-semibold [overflow-wrap:anywhere]">
            Terdeteksi dari &ldquo;{result.title}&rdquo; ({result.seconds} detik pertama):
          </p>
          {keys.length ? (
            <ul className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
              {keys.map((k) => {
                const label = STYLE_FIELDS.find((f) => f.key === k)?.label ?? k;
                const changed = current[k] !== result.style[k];
                return (
                  <li key={k} className="flex items-center gap-1.5">
                    {(k === "caption_color" || k === "caption_base") && (
                      <span
                        className="size-3 flex-none rounded-full border"
                        style={{ background: CAPTION_COLORS[String(result.style[k])] }}
                      />
                    )}
                    <span className="text-muted-foreground">{label}:</span>
                    <span className={cn(changed ? "font-semibold text-foreground" : "text-muted-foreground")}>
                      {describe(k, result.style[k])}
                    </span>
                    {!changed && <span className="text-muted-foreground">(sama)</span>}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted-foreground">Tidak ada gaya yang bisa dibaca dari clip ini.</p>
          )}
          {result.notes.map((n) => (
            <p key={n} className="text-muted-foreground">
              {n}
            </p>
          ))}
          {keys.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" onClick={apply}>
                Terapkan gaya ini
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPreview((v) => !v)}>
                {preview ? <EyeOffIcon /> : <EyeIcon />} {preview ? "Tutup pratinjau" : "Pratinjau dulu"}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setResult(null)}>
                Buang
              </Button>
            </div>
          )}
          {preview && <StylePreview style={{ ...current, ...result.style }} />}
        </div>
      )}
    </div>
  );
}

function StyleControl({
  field,
  style,
  onChange,
}: {
  field: StyleField;
  style: Style;
  onChange: <K extends keyof Style>(key: K, value: Style[K]) => void;
}) {
  const value = style[field.key];
  const set = (v: unknown) => onChange(field.key, v as Style[typeof field.key]);

  if (field.type === "bool") {
    return (
      <Label className="cursor-pointer self-end py-1.5 font-normal">
        <Checkbox checked={Boolean(value)} onCheckedChange={(v) => set(v === true)} />
        {field.label}
      </Label>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs font-normal text-muted-foreground">{field.label}</Label>
      {field.type === "select" && (
        <SimpleSelect
          value={value as string | number}
          onChange={set}
          options={field.options}
          aria-label={field.label}
        />
      )}
      {field.type === "range" && <RangeControl field={field} value={Number(value)} onCommit={set} />}
      {field.type === "text" && (
        <CommitInput value={String(value ?? "")} onCommit={set} placeholder={field.placeholder} />
      )}
      {field.type === "color" && (
        <div className="flex flex-wrap gap-2 py-0.5">
          {Object.entries(CAPTION_COLORS).map(([name, color]) => (
            <button
              key={name}
              type="button"
              title={name}
              aria-label={`Warna ${name}`}
              aria-pressed={value === name}
              onClick={() => set(name)}
              style={{ background: color }}
              className={cn(
                "size-7 rounded-full border-2 border-transparent transition-transform hover:scale-110",
                value === name && "border-white shadow-[inset_0_0_0_2px_var(--background)]",
              )}
            />
          ))}
        </div>
      )}
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

/** Satu frame contoh dari video terbaru (atau latar contoh) dengan gaya saat ini. */
function StylePreview({ style }: { style: Style }) {
  const { state } = useStore();
  const [img, setImg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const source = state.projects.find((p) => p.status === "siap" && p.source);

  useEffect(() => {
    let stale = false;
    let url: string | null = null;
    const t = window.setTimeout(async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/preview-style`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ style }),
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
  }, [style]);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="aspect-[9/16] w-56 max-w-full overflow-hidden rounded-xl border bg-black">
        {img && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={img}
            alt="Pratinjau gaya video"
            className={cn("size-full object-cover transition-opacity", loading && "opacity-45")}
          />
        )}
      </div>
      <span className="text-center text-xs text-muted-foreground">
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
