"use client";

import { FolderOpenIcon, ScissorsIcon, SettingsIcon, WifiOffIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";

import { useStore } from "./store";

export function AppHeader() {
  const { state, online, setSettingsOpen } = useStore();
  return (
    <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5 text-xl font-extrabold tracking-tight">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <ScissorsIcon className="size-4" />
          </span>
          ClipMaker
        </div>
        {online ? (
          <Badge variant="outline" className="text-muted-foreground">
            Antrian: {state.queue}
          </Badge>
        ) : (
          <Badge variant="destructive">
            <WifiOffIcon /> Terputus dari aplikasi
          </Badge>
        )}
        <div className="flex-1" />
        <Button
          variant="outline"
          aria-label="Folder hasil"
          onClick={() => post("/api/open-folder", { path: "" }).catch(() => {})}
        >
          <FolderOpenIcon />
          <span className="hidden sm:inline">Folder hasil</span>
        </Button>
        <Button variant="outline" aria-label="Pengaturan" onClick={() => setSettingsOpen(true)}>
          <SettingsIcon />
          <span className="hidden sm:inline">Pengaturan</span>
        </Button>
      </div>
    </header>
  );
}
