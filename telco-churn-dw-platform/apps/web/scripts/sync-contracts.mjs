// Copy the shared JSON Schemas into the app so browser validation uses exactly
// the same contract as the server.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const candidates = [join(here, "../../../contracts"), join(here, "../contracts-src")];
const src = candidates.find((p) => existsSync(join(p, "telco-record.v1.schema.json")));
if (!src) {
  console.error("contracts directory not found");
  process.exit(1);
}
const dest = join(here, "../src/contracts");
mkdirSync(dest, { recursive: true });
for (const f of ["telco-record.v1.schema.json", "ingest-batch.v1.schema.json", "ingest-batch-result.v1.schema.json"]) {
  cpSync(join(src, f), join(dest, f));
}
console.log(`contracts synced from ${src}`);
