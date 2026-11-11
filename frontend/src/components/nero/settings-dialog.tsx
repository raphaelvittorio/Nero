"use client";

import { TrashIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SimpleSelect, type Option } from "@/components/fields";
import { Button } from "@/components/ui/button";
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
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { useNero, type GlobalSettings } from "./store";

/** "" (tidak memakai cookies) disimpan sebagai "none" karena Select butuh nilai tidak kosong. */
const COOKIE_BROWSERS: Option<string>[] = [
  ["none", "Tidak"],
  ["chrome", "chrome"],
  ["edge", "edge"],
  ["firefox", "firefox"],
  ["brave", "brave"],
];

/** Pengaturan umum Nero: berlaku untuk semua fitur. */
export function SettingsDialog() {
  const { settings, settingsOpen, setSettingsOpen } = useNero();
  return (
    <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
      <DialogContent className="sm:max-w-xl">
        {settings && settingsOpen && <SettingsForm settings={settings} />}
      </DialogContent>
    </Dialog>
  );
}

function SettingsForm({ settings }: { settings: GlobalSettings }) {
  const { setSettingsOpen, loadSettings } = useNero();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(settings.ai_model);
  const [cookie, setCookie] = useState(settings.cookies_browser || "none");

  async function save() {
    try {
      await post("/api/settings", {
        api_key: key,
        ai_model: model.trim(),
        cookies_browser: cookie === "none" ? "" : cookie,
      });
      setSettingsOpen(false);
      await loadSettings();
      toast.success("Pengaturan disimpan");
    } catch {}
  }

  async function clearKey() {
    try {
      await post("/api/settings", { clear_key: true });
      setSettingsOpen(false);
      await loadSettings();
      toast.success("API key dihapus");
    } catch {}
  }

  const field = "flex flex-col gap-1.5";
  return (
    <>
      <DialogHeader>
        <DialogTitle>Pengaturan Nero</DialogTitle>
        <DialogDescription>Berlaku untuk semua fitur. Disimpan hanya di komputer Anda.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-4">
        <div className={field}>
          <Label htmlFor="s_key">Claude API key (opsional: membuat hasil setiap fitur jauh lebih pintar)</Label>
          <Input
            id="s_key"
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-ant-..."
          />
          <span className={cn("text-xs", settings.has_key ? "text-ok" : "text-muted-foreground")}>
            {settings.has_key
              ? "✓ API key tersimpan. Kosongkan untuk tetap memakai yang lama."
              : "Belum ada API key. Buat di console.anthropic.com (berbayar per pemakaian)."}
          </span>
        </div>
        <div className={field}>
          <Label htmlFor="s_model">Model AI</Label>
          <Input id="s_model" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div className={field}>
          <Label>
            Ambil cookies dari browser (isi bila YouTube minta login / &ldquo;confirm you&rsquo;re not a bot&rdquo;)
          </Label>
          <SimpleSelect value={cookie} onChange={setCookie} options={COOKIE_BROWSERS} aria-label="Cookies browser" />
        </div>
      </div>
      <DialogFooter className="sm:justify-between">
        <Button variant="destructive" size="sm" onClick={clearKey} disabled={!settings.has_key}>
          <TrashIcon /> Hapus API key
        </Button>
        <Button onClick={save}>Simpan</Button>
      </DialogFooter>
    </>
  );
}
