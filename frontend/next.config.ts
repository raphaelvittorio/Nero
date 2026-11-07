import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Backend Python (app.py). Saat `npm run dev`, permintaan API diteruskan ke sini.
const FLASK = process.env.CLIPMAKER_API ?? "http://127.0.0.1:7860";

export default function config(phase: string): NextConfig {
  // Tanpa cacheComponents/PPR: tidak bisa dipakai bersama output "export",
  // dan semua data halaman memang datang dari Flask di sisi browser.
  const base: NextConfig = {
    turbopack: {
      rules: {
        "*.css": {
          loaders: ["@tailwindcss/turbopack"],
          as: "*.css",
        },
      },
    },
  };

  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...base,
      async rewrites() {
        return ["/api/:path*", "/media/:path*", "/out/:path*"].map((source) => ({
          source,
          destination: FLASK + source,
        }));
      },
    };
  }

  // `npm run build`: halaman statis biasa yang disajikan Flask dari folder web/.
  return { ...base, output: "export", images: { unoptimized: true } };
}
