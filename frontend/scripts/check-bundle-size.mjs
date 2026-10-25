// Fails when the JavaScript the app loads grows past its budget (gzip sizes, like the browser downloads them).
// Raise a budget on purpose, in a commit that says why, never to get a build through.
//
// Two measures are printed and both are checked:
//  1. FIRST LOAD: the scripts out/index.html (the page behind /app/) asks for. This is what a person waits for on a cold load, and what
//     the code-splitting of the screens (React.lazy) and of the board (dnd-kit) keeps small.
//  2. TOTAL and LARGEST FILE: every script of the export together. Splitting moves code out of the first load but does not remove it, so
//     the total stays about the same; this guards against the whole app growing, and the file budget against one script swallowing the rest.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

// Set just above the numbers of the current build (167.7 first load, 381.7 total, 67.3 largest). Why these:
//  - The first load is what a person waits for. It went from 176.4 to 167.7 kB although the dashboard gained the tabs, filter panel,
//    action menu, preferences and the persisted query cache, because every other screen and the board (dnd-kit) are now their own chunks.
//    About 142 kB of it is Next.js and React themselves, which nothing in this app can shrink.
//  - The total grew (331.6 to 381.7 kB) on purpose: it now holds the new features plus the cost of splitting into 37 files instead of 18.
//    It is no longer a measure of what a person downloads; the first-load budget is. The file budget fell from 100 to 70 kB.
//  - The total went on to 413 kB with the ATS check and CV builder, the AI helpers, job management, the Help page and the
//    statistics screens, each its own lazily loaded chunk: a person only downloads the screens they open. The budget is 430 so the
//    next screen is a deliberate decision, while the first-load budget (168 kB now, limit 172) is what keeps the app quick to open.
const FIRST_LOAD_BUDGET_KB = Number(process.env.BUNDLE_FIRST_LOAD_KB || 172);
const TOTAL_BUDGET_KB = Number(process.env.BUNDLE_TOTAL_KB || 430);
const FILE_BUDGET_KB = Number(process.env.BUNDLE_FILE_KB || 70);

function scripts(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? scripts(path) : path.endsWith(".js") ? [path] : [];
  });
}

const gzipKb = (path) => gzipSync(readFileSync(path)).length / 1024;

/** The script files an HTML page references (src="/app/_next/static/..."), as paths inside out/. */
export function referencedScripts(html) {
  const found = new Set();
  for (const m of html.matchAll(/(?:src|href)="(?:\/app)?\/(_next\/static\/[^"?#]+\.js)"/g)) found.add(m[1]);
  return [...found];
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/").split("/").pop())) {
  const files = scripts("out/_next/static").map((path) => ({ path, kb: gzipKb(path) }));
  if (files.length === 0) {
    console.error("No build found in out/. Run `pnpm build` first.");
    process.exit(1);
  }
  const total = files.reduce((sum, f) => sum + f.kb, 0);
  const largest = files.reduce((a, b) => (b.kb > a.kb ? b : a));

  const firstLoadFiles = referencedScripts(readFileSync("out/index.html", "utf8")).filter((p) => files.some((f) => f.path.replace(/\\/g, "/") === `out/${p}`));
  const firstLoad = firstLoadFiles.reduce((sum, p) => sum + gzipKb(join("out", p)), 0);

  console.log(`First load of /app/: ${firstLoad.toFixed(1)} kB gzip in ${firstLoadFiles.length} scripts (budget ${FIRST_LOAD_BUDGET_KB}).`);
  console.log(`All JavaScript: ${total.toFixed(1)} kB gzip in ${files.length} files (budget ${TOTAL_BUDGET_KB}); largest ${largest.kb.toFixed(1)} kB ${largest.path} (budget ${FILE_BUDGET_KB}).`);
  if (firstLoadFiles.length === 0) {
    console.error("Could not find the scripts out/index.html loads.");
    process.exit(1);
  }
  if (firstLoad > FIRST_LOAD_BUDGET_KB || total > TOTAL_BUDGET_KB || largest.kb > FILE_BUDGET_KB) {
    console.error("Over budget.");
    process.exit(1);
  }
}
