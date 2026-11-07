"use client";

import { ChevronRightIcon, EyeIcon, EyeOffIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { post } from "@/lib/api";
import { CAPTION_COLORS, STYLE_FIELDS, type StyleField } from "@/lib/options";
import type { Style } from "@/lib/types";
import { cn } from "@/lib/utils";

import { CommitInput, SimpleSelect } from "./fields";
import { useStore } from "./store";

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
      await post("/api/settings", { style: { [key]: value } });
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
        const r = await fetch("/api/preview-style", {
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
