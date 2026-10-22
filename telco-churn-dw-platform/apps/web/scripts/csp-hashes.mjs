// Collect SHA-256 hashes of every inline <script> in the static export so the
// Content-Security-Policy can allow exactly those scripts (no 'unsafe-inline').
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [, , dir = "out", outFile = "nginx/csp-hashes.txt"] = process.argv;
const hashes = new Set();
const walk = (d) => {
  for (const f of readdirSync(d)) {
    const p = join(d, f);
    if (statSync(p).isDirectory()) walk(p);
    else if (p.endsWith(".html")) {
      const html = readFileSync(p, "utf8");
      for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)) {
        if (m[1].length) hashes.add(`'sha256-${createHash("sha256").update(m[1]).digest("base64")}'`);
      }
    }
  }
};
walk(dir);
writeFileSync(outFile, [...hashes].sort().join(" "));
console.log(`${hashes.size} inline script hashes written to ${outFile}`);
