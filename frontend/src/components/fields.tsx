"use client";

import { useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/** Pilihan untuk SimpleSelect: [nilai, label]. */
export type Option<V> = readonly [V, string];

/** Select sederhana dari daftar [nilai, label]. */
export function SimpleSelect<V extends string | number>({
  value,
  onChange,
  options,
  className,
  size,
  ...rest
}: {
  value: V;
  onChange: (v: V) => void;
  options: readonly Option<V>[];
  className?: string;
  size?: "sm" | "default";
  "aria-label"?: string;
  id?: string;
}) {
  const items = options.map(([v, label]) => ({ value: v, label }));
  return (
    <Select items={items} value={value} onValueChange={(v) => v !== null && onChange(v as V)}>
      <SelectTrigger className={cn("w-full", className)} size={size} {...rest}>
        <SelectValue />
      </SelectTrigger>
      {/* boleh lebih lebar dari tombolnya supaya label panjang tidak terpotong */}
      <SelectContent className="w-auto min-w-(--anchor-width) max-w-[min(34rem,var(--available-width))]">
        {items.map((it) => (
          <SelectItem key={String(it.value)} value={it.value}>
            {it.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * Input yang menyimpan saat fokus lepas atau Enter ditekan (Esc membatalkan).
 * Selama diketik, nilainya tidak ditimpa oleh pembaruan status berkala.
 */
export function CommitInput({
  value,
  onCommit,
  className,
  ...props
}: { value: string; onCommit: (v: string) => void } & Omit<
  React.ComponentProps<"input">,
  "value" | "onChange" | "onBlur" | "onFocus"
>) {
  const [draft, setDraft] = useState<string | null>(null);
  const cancelled = useRef(false);
  return (
    <Input
      {...props}
      className={className}
      value={draft ?? value}
      onFocus={() => setDraft(value)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (!cancelled.current && draft !== null && draft !== value) onCommit(draft);
        cancelled.current = false;
        setDraft(null);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          cancelled.current = true;
          e.currentTarget.blur();
        }
      }}
    />
  );
}
