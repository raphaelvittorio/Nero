"use client";

import { LinkIcon, MapPinIcon, MessageSquareTextIcon, PinIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Textarea } from "@/components/ui/textarea";
import { fmt } from "@/lib/api";
import type { BriefSummary } from "@/lib/types";

const PLACEHOLDER = `Satu baris = satu referensi. Contoh:
12:30 - 13:45 cerita gagal bisnis pertama
1:02:10 - 1:03:00 tips mengatur uang
45:20 momen lucu
https://www.tiktok.com/@akun/video/...  (clip referensi)
Fokus pada momen tentang "investasi". Jangan ambil bagian sponsor.`;

/** Kolom "Referensi & instruksi": timeline riset, titik waktu, link clip referensi, dan instruksi bebas. */
export function BriefField({
  value,
  onChange,
  hasKey,
  id,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  hasKey: boolean;
  id?: string;
  autoFocus?: boolean;
}) {
  const summary = useBriefSummary(value);
  return (
    <div className="flex flex-col gap-2">
      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={PLACEHOLDER}
        autoFocus={autoFocus}
        spellCheck={false}
        className="min-h-36 text-[13px] leading-relaxed"
      />
      {summary && <SummaryList s={summary} hasKey={hasKey} />}
      <p className="text-xs leading-relaxed text-muted-foreground">
        <b className="text-foreground">Timeline</b> (<code>mm:ss - mm:ss</code> atau <code>j:mm:ss</code>) dan{" "}
        <b className="text-foreground">link clip referensi</b> yang ditemukan di video ini selalu dijadikan clip.{" "}
        <b className="text-foreground">Titik waktu</b> (<code>45:20</code>) dibuatkan clip di sekitarnya. Sisa{" "}
        <i>Jumlah clip</i> diisi otomatis; isi Jumlah clip sama dengan banyaknya timeline bila hanya ingin clip
        dari riset Anda. Baris lain menjadi <b className="text-foreground">instruksi</b>
        {hasKey ? " untuk Claude." : " (tanpa API key dipakai sebagai kata kunci topik)."}
      </p>
    </div>
  );
}

function useBriefSummary(text: string): BriefSummary | null {
  const [summary, setSummary] = useState<BriefSummary | null>(null);
  useEffect(() => {
    if (!text.trim()) return;
    const ctl = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const r = await fetch("/api/parse-brief", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
          signal: ctl.signal,
        });
        if (r.ok) setSummary((await r.json()) as BriefSummary);
      } catch {}
    }, 350);
    return () => {
      window.clearTimeout(timer);
      ctl.abort();
    };
  }, [text]);
  return text.trim() ? summary : null;
}

function SummaryList({ s, hasKey }: { s: BriefSummary; hasKey: boolean }) {
  const items: { icon: React.ReactNode; text: string; key: string }[] = [
    ...s.ranges.map((r, i) => ({
      key: `r${i}`,
      icon: <PinIcon className="text-primary" />,
      text: `${fmt(r.start)} → ${fmt(r.end)}${r.end <= r.start ? " (selesai harus setelah mulai!)" : ""}${r.note ? ` · ${r.note}` : ""}`,
    })),
    ...s.points.map((p, i) => ({
      key: `p${i}`,
      icon: <MapPinIcon className="text-primary" />,
      text: `sekitar ${fmt(p.t)}${p.note ? ` · ${p.note}` : ""}`,
    })),
    ...s.links.map((l, i) => ({
      key: `l${i}`,
      icon: <LinkIcon className="text-primary" />,
      text:
        (/[?&#](t|start)=/.test(l) ? "link ber-waktu (jadi titik waktu bila videonya sama): " : "clip referensi: ") +
        l.replace(/^https?:\/\/(www\.)?/, "").slice(0, 60),
    })),
  ];
  const kw = [
    s.keywords.length ? `cari: ${s.keywords.join(", ")}` : "",
    s.avoid.length ? `hindari: ${s.avoid.join(", ")}` : "",
  ].filter(Boolean);
  if (s.instructions)
    items.push({
      key: "i",
      icon: <MessageSquareTextIcon className="text-primary" />,
      text: hasKey ? `instruksi untuk Claude${kw.length ? ` (${kw.join("; ")})` : ""}` : kw.join("; ") || "instruksi",
    });
  if (!items.length) return null;
  const shown = items.slice(0, 8);
  return (
    <ul className="flex flex-col gap-1 rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
      <li className="font-semibold text-foreground">Dikenali:</li>
      {shown.map((it) => (
        <li key={it.key} className="flex items-start gap-1.5 [&_svg]:mt-px [&_svg]:size-3.5 [&_svg]:flex-none">
          {it.icon}
          <span className="[overflow-wrap:anywhere]">{it.text}</span>
        </li>
      ))}
      {items.length > shown.length && <li>+{items.length - shown.length} lagi</li>}
    </ul>
  );
}
