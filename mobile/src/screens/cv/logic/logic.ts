/** Small pure helpers for the CV screens: a safe Markdown reader (the same subset the server's export understands) and diff counts. */

export type Block = { kind: "h1" | "h2" | "h3" | "li" | "p" | "hr"; text: string };
export type Inline = { kind: "text" | "strong" | "em" | "link"; text: string; href?: string };

const BULLET = /^\s*(?:[-*•])\s+(.*)$/;
const HEADING = /^(#{1,3})\s+(.*)$/;
const RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
const INLINE = /\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;

export function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim()) continue;
    if (RULE.test(line)) {
      blocks.push({ kind: "hr", text: "" });
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: `h${heading[1].length}` as Block["kind"], text: heading[2].trim() });
      continue;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      blocks.push({ kind: "li", text: bullet[1].trim() });
      continue;
    }
    blocks.push({ kind: "p", text: line.trim() });
  }
  return blocks;
}

/** Splits a line into plain, bold, italic and http(s) link pieces. Everything is returned as text for React to escape, never as HTML. */
export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let pos = 0;
  for (const m of text.matchAll(INLINE)) {
    const start = m.index ?? 0;
    if (start > pos) out.push({ kind: "text", text: text.slice(pos, start) });
    if (m[1] !== undefined) out.push({ kind: "strong", text: m[1] });
    else if (m[2] !== undefined) out.push({ kind: "em", text: m[2] });
    else out.push({ kind: "link", text: m[3], href: m[4] });
    pos = start + m[0].length;
  }
  if (pos < text.length) out.push({ kind: "text", text: text.slice(pos) });
  return out;
}

export type DiffRow = { tag: "same" | "del" | "add"; text: string };

export function diffCounts(rows: DiffRow[]): { added: number; removed: number; same: number } {
  const n = { added: 0, removed: 0, same: 0 };
  for (const r of rows) {
    if (r.tag === "add") n.added += 1;
    else if (r.tag === "del") n.removed += 1;
    else n.same += 1;
  }
  return n;
}

/** One plain sentence about how two versions differ. */
export function diffSummary(rows: DiffRow[]): string {
  const { added, removed } = diffCounts(rows);
  if (added === 0 && removed === 0) return "These two versions are the same.";
  const part = (n: number, what: string) => `${n} line${n === 1 ? "" : "s"} ${what}`;
  return `${[added ? part(added, "added") : "", removed ? part(removed, "removed") : ""].filter(Boolean).join(", ")}.`;
}

/** What the fact check found, in a sentence a person can act on. */
export type Finding = { kind: string; text: string; line: number };
export function findingText(f: Finding): string {
  if (f.kind === "number") return `Number ${f.text}`;
  if (f.kind === "name") return `Name or term ${f.text}`;
  return `The job asks for ${f.text}, which your material never mentions`;
}
