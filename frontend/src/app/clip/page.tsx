import type { Metadata } from "next";

import { ClipApp } from "@/features/clip/clip-app";

export const metadata: Metadata = { title: "Clip Maker" };

export default function Page() {
  return <ClipApp />;
}
