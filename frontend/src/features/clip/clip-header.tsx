"use client";

import { FolderOpenIcon, ScissorsIcon, SettingsIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { openFolder } from "@/lib/api";

import { OUT_DIR } from "./api";
import { useStore } from "./store";

export function ClipHeader() {
  const { state, setSettingsOpen } = useStore();
  return (
    <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-foreground text-background">
          <ScissorsIcon className="size-4" />
        </span>
        <div className="min-w-0">
          <h1 className="text-lg leading-tight font-extrabold tracking-tight">Clip Maker</h1>
          <p className="hidden truncate text-xs text-muted-foreground sm:block">
            Video panjang jadi clip pendek siap upload
          </p>
        </div>
        <Badge variant="outline" className="text-muted-foreground">
          Antrian: {state.queue}
        </Badge>
        <div className="flex-1" />
        <Button variant="outline" aria-label="Folder hasil Clip Maker" onClick={() => openFolder(OUT_DIR)}>
          <FolderOpenIcon />
          <span className="hidden sm:inline">Folder hasil</span>
        </Button>
        <Button variant="outline" aria-label="Pengaturan Clip Maker" onClick={() => setSettingsOpen(true)}>
          <SettingsIcon />
          <span className="hidden sm:inline">Pengaturan clip</span>
        </Button>
      </div>
    </header>
  );
}
