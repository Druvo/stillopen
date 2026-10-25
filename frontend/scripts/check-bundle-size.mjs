// Fails when the JavaScript the app loads grows past its budget (gzip sizes, like the browser downloads them).
// Raise a budget on purpose, in a commit that says why, never to get a build through.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const TOTAL_BUDGET_KB = Number(process.env.BUNDLE_TOTAL_KB || 350); // every script of the export together
const FILE_BUDGET_KB = Number(process.env.BUNDLE_FILE_KB || 100); // the largest single script

function scripts(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? scripts(path) : path.endsWith(".js") ? [path] : [];
  });
}

const files = scripts("out/_next/static").map((path) => ({ path, kb: gzipSync(readFileSync(path)).length / 1024 }));
if (files.length === 0) {
  console.error("No build found in out/. Run `pnpm build` first.");
  process.exit(1);
}
const total = files.reduce((sum, f) => sum + f.kb, 0);
const largest = files.reduce((a, b) => (b.kb > a.kb ? b : a));
console.log(`JavaScript: ${total.toFixed(1)} kB gzip in ${files.length} files (budget ${TOTAL_BUDGET_KB}); largest ${largest.kb.toFixed(1)} kB ${largest.path} (budget ${FILE_BUDGET_KB}).`);
if (total > TOTAL_BUDGET_KB || largest.kb > FILE_BUDGET_KB) {
  console.error("Over budget.");
  process.exit(1);
}
