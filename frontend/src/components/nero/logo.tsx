import Link from "next/link";

import { cn } from "@/lib/utils";

/** Tanda Nero: kotak putih dengan huruf N hitam. */
export function NeroMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7 shrink-0", className)}>
      <rect width="32" height="32" rx="8" className="fill-foreground" />
      <path className="fill-background" d="M9 23V9h2.7l8.6 9.9V9H23v14h-2.7l-8.6-9.9V23z" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn("flex items-center gap-2.5 text-lg font-extrabold tracking-tight", className)}
      aria-label="Nero, ke Beranda"
    >
      <NeroMark />
      Nero
    </Link>
  );
}
