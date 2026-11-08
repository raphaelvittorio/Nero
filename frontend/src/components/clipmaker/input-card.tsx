"use client";

import { ChevronDownIcon, PlayIcon, TargetIcon, UploadIcon } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { post } from "@/lib/api";
import { LANGUAGES } from "@/lib/options";
import { cn } from "@/lib/utils";

import { BriefField } from "./brief-field";
import { SimpleSelect } from "./fields";
import { useStore } from "./store";

export function InputCard() {
  const { settings, nClips, setNClips, language, setLanguage, refresh } = useStore();
  const [links, setLinks] = useState("");
  const [brief, setBrief] = useState("");
  const [briefOpen, setBriefOpen] = useState(false);
  const [autoRender, setAutoRender] = useState(false);
  const [over, setOver] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const fileIn = useRef<HTMLInputElement>(null);

  async function submitLinks() {
    if (!links.trim()) {
      toast("Tempel link video dulu");
      return;
    }
    setSending(true);
    try {
      const r = await post("/api/add", { links, n_clips: nClips, auto_render: autoRender, language, brief });
      setLinks("");
      setBrief(""); // timeline riset berlaku untuk video yang barusan diproses
      toast.success(`${r.count} video masuk antrian`);
      refresh();
    } catch {
    } finally {
      setSending(false);
    }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length) return;
    try {
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        fd.append("n_clips", String(nClips));
        fd.append("auto_render", String(autoRender));
        fd.append("language", language);
        fd.append("brief", brief);
        setUploading(f.name);
        await post("/api/upload", fd);
      }
      setBrief("");
      toast.success("File masuk antrian");
    } catch {
    } finally {
      setUploading(null);
      if (fileIn.current) fileIn.current.value = "";
      refresh();
    }
  }

  const gpu = settings?.gpu;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">1. Masukkan video</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Textarea
          value={links}
          onChange={(e) => setLinks(e.target.value)}
          className="min-h-24"
          placeholder="Tempel link video di sini (YouTube, TikTok, Instagram, Facebook, X, dll). Satu link per baris untuk proses banyak video sekaligus."
        />
        <button
          type="button"
          disabled={uploading !== null}
          onClick={() => fileIn.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            uploadFiles(e.dataTransfer.files);
          }}
          className={cn(
            "flex items-center justify-center gap-2 rounded-xl border-[1.5px] border-dashed p-3.5 text-sm text-muted-foreground transition-colors hover:text-foreground",
            over && "border-primary text-foreground",
          )}
        >
          <UploadIcon className="size-4" />
          {uploading ? (
            <span>Mengunggah {uploading}...</span>
          ) : (
            <span>
              atau <b className="text-foreground">klik / tarik file video</b> dari komputer
            </span>
          )}
        </button>
        <input
          ref={fileIn}
          type="file"
          accept="video/*"
          multiple
          hidden
          onChange={(e) => uploadFiles(e.target.files)}
        />

        <Collapsible open={briefOpen} onOpenChange={setBriefOpen} className="rounded-xl border">
          <CollapsibleTrigger className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm font-medium">
            <TargetIcon className="size-4 text-primary" />
            <span>Referensi & instruksi</span>
            <span className="text-xs font-normal text-muted-foreground">
              (opsional: timeline riset, link clip contoh, prompt)
            </span>
            {brief.trim() && !briefOpen && <span className="size-2 rounded-full bg-primary" title="Sudah diisi" />}
            <ChevronDownIcon
              className={cn("ml-auto size-4 text-muted-foreground transition-transform", briefOpen && "rotate-180")}
            />
          </CollapsibleTrigger>
          <CollapsibleContent className="px-3.5 pb-3.5">
            <BriefField value={brief} onChange={setBrief} hasKey={Boolean(settings?.has_key)} id="brief" />
            {links.trim().split(/\s+/).filter((l) => l.startsWith("http")).length > 1 && brief.trim() && (
              <p className="mt-2 text-xs text-warn">
                Referensi ini dipakai untuk semua link di atas. Timeline riset sebaiknya diproses satu video sekali.
              </p>
            )}
          </CollapsibleContent>
        </Collapsible>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 pt-1">
          <div className="flex items-center gap-2">
            <Label htmlFor="nclips">Jumlah clip</Label>
            <Input
              id="nclips"
              type="number"
              min={1}
              max={20}
              value={nClips}
              onChange={(e) => setNClips(Number(e.target.value) || 1)}
              className="w-16"
            />
          </div>
          <div className="flex items-center gap-2">
            <Label>Bahasa</Label>
            <SimpleSelect
              value={language}
              onChange={setLanguage}
              options={LANGUAGES}
              className="w-auto min-w-36"
              aria-label="Bahasa yang diucapkan di video"
            />
          </div>
          <Label className="cursor-pointer">
            <Checkbox checked={autoRender} onCheckedChange={(v) => setAutoRender(v === true)} />
            Langsung render otomatis
          </Label>
          <div className="flex-1" />
          <Button size="lg" className="px-4 font-bold" onClick={submitLinks} disabled={sending}>
            Proses <PlayIcon />
          </Button>
        </div>

        {settings && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {settings.has_key
              ? "🤖 Mode AI aktif: momen, judul & caption dipilih oleh Claude."
              : "⚡ Mode lokal: momen dipilih otomatis di komputer Anda (gratis). Tambahkan Claude API key di Pengaturan untuk hasil lebih pintar."}
            <br />
            {gpu?.device === "cuda"
              ? "🚀 Transkrip memakai GPU NVIDIA."
              : `🐢 Transkrip memakai CPU${gpu?.error ? ` (GPU gagal dipakai: ${gpu.error})` : ""}.`}
            {gpu?.encoder === "h264_nvenc" ? " Encode video memakai GPU (NVENC)." : " Encode video memakai CPU."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
