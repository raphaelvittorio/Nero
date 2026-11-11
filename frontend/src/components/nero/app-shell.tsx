"use client";

import { FolderOpenIcon, HomeIcon, SettingsIcon, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { FEATURES } from "@/features";
import { openFolder } from "@/lib/api";
import { cn } from "@/lib/utils";

import { Logo } from "./logo";
import { SettingsDialog } from "./settings-dialog";
import { NeroProvider, useNero } from "./store";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** id fitur, untuk menampilkan jumlah tugas yang sedang berjalan */
  feature?: string;
}

const HOME: NavItem = { href: "/", label: "Beranda", icon: HomeIcon };
const FEATURE_ITEMS: NavItem[] = FEATURES.map((f) => ({ href: f.href, label: f.name, icon: f.icon, feature: f.id }));

/** Kerangka semua halaman: menu samping (layar lebar) atau bilah atas (layar kecil). */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <NeroProvider>
      <div className="flex min-h-svh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <MobileBar />
          {children}
        </div>
      </div>
      <SettingsDialog />
    </NeroProvider>
  );
}

function useActive() {
  const path = usePathname().replace(/\/+$/, "") || "/";
  return (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(href + "/"));
}

function Sidebar() {
  const isActive = useActive();
  const { setSettingsOpen } = useNero();
  return (
    <aside className="sticky top-0 hidden h-svh w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
      <div className="flex h-16 items-center px-5">
        <Logo />
      </div>
      <nav className="flex flex-col gap-0.5 px-3" aria-label="Menu utama">
        <SideLink item={HOME} active={isActive(HOME.href)} />
        <p className="px-2.5 pt-5 pb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
          Fitur
        </p>
        {FEATURE_ITEMS.map((it) => (
          <SideLink key={it.href} item={it} active={isActive(it.href)} />
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-0.5 border-t border-sidebar-border p-3">
        <SideButton icon={FolderOpenIcon} onClick={() => openFolder()}>
          Folder hasil
        </SideButton>
        <SideButton icon={SettingsIcon} onClick={() => setSettingsOpen(true)}>
          Pengaturan
        </SideButton>
        <Status className="px-2.5 pt-2.5 pb-1" />
      </div>
    </aside>
  );
}

const itemClass =
  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground";

function SideLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(itemClass, active && "bg-sidebar-accent text-foreground")}
    >
      <Icon className="size-4" />
      <span className="flex-1">{item.label}</span>
      {item.feature && <BusyCount feature={item.feature} />}
    </Link>
  );
}

function SideButton({ icon: Icon, children, onClick }: { icon: LucideIcon; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={cn(itemClass, "w-full text-left")}>
      <Icon className="size-4" />
      {children}
    </button>
  );
}

/** Jumlah tugas fitur yang sedang berjalan (kosong bila tidak ada). */
function BusyCount({ feature }: { feature: string }) {
  const busy = useNero().summaries[feature]?.busy ?? 0;
  if (!busy) return null;
  return (
    <span
      className="flex items-center gap-1 rounded-full bg-foreground px-1.5 text-[11px] font-semibold text-background tabular-nums"
      title={`${busy} sedang berjalan`}
    >
      <span className="size-1.5 animate-[pulse-dot_1.2s_ease-in-out_infinite] rounded-full bg-background" />
      {busy}
    </span>
  );
}

/** Tanda koneksi ke app.py dan mode AI. */
function Status({ className }: { className?: string }) {
  const { online, settings, setSettingsOpen } = useNero();
  return (
    <div className={cn("flex flex-col gap-1 text-xs text-muted-foreground", className)}>
      <span className="flex items-center gap-2">
        <span className={cn("size-1.5 rounded-full", online ? "bg-ok" : "bg-destructive")} />
        {online ? "Terhubung" : "Terputus: buka run.bat"}
      </span>
      {settings && (
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-2 text-left hover:text-foreground"
        >
          <span className={cn("size-1.5 rounded-full", settings.has_key ? "bg-foreground" : "bg-muted-foreground/50")} />
          {settings.has_key ? "AI Claude aktif" : "Mode lokal (tanpa AI)"}
        </button>
      )}
    </div>
  );
}

function MobileBar() {
  const isActive = useActive();
  const { online, setSettingsOpen } = useNero();
  return (
    <header className="border-b lg:hidden">
      <div className="flex items-center gap-2 px-4 pt-3 pb-2">
        <Logo />
        {!online && <span className="ml-1 text-xs text-destructive">Terputus</span>}
        <div className="flex-1" />
        <Button variant="ghost" size="icon" aria-label="Folder hasil" onClick={() => openFolder()}>
          <FolderOpenIcon />
        </Button>
        <Button variant="ghost" size="icon" aria-label="Pengaturan" onClick={() => setSettingsOpen(true)}>
          <SettingsIcon />
        </Button>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label="Menu utama">
        {[HOME, ...FEATURE_ITEMS].map((it) => {
          const Icon = it.icon;
          const active = isActive(it.href);
          return (
            <Link
              key={it.href}
              href={it.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground",
                active ? "bg-accent text-foreground" : "hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {it.label}
              {it.feature && <BusyCount feature={it.feature} />}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
