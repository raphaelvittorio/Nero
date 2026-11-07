// Salin hasil `next build` (folder out/) ke ../web, folder yang disajikan app.py.
import { cpSync, existsSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

const out = fileURLToPath(new URL("../out/", import.meta.url));
const web = fileURLToPath(new URL("../../web/", import.meta.url));

if (!existsSync(out + "index.html")) {
  console.error("out/index.html tidak ada. Jalankan `next build` dulu.");
  process.exit(1);
}
rmSync(web, { recursive: true, force: true });
cpSync(out, web, { recursive: true });
console.log("Tampilan disalin ke", web);
