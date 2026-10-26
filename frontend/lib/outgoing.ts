// Turns a drafted note (Markdown, as the server writes it for the owner to review)
// into the plain message the owner actually sends from WhatsApp or email.
//
// The server's draft carries things meant for the owner, not the buyer: a DRAFT
// banner, a title line, an "assumptions" section, open points about the
// statute sheet and a disclaimer footer. None of that belongs in a message to a
// buyer. This only removes and re-flows text: every figure, date and sentence
// that stays is the server's own, word for word (apart from dash style).

/** Sections the server writes for the owner; dropped from the outgoing message. */
const OWNER_ONLY = /^#{1,6}\s*(assumptions\b|open points\b)/i;

// Em and en dash, built from code points so this file itself carries no long dash.
const LONG_DASH = new RegExp("[ \t]*[" + String.fromCharCode(0x2014, 0x2013) + "][ \t]*", "g");

function dashes(line: string): string {
  // A long dash reads as machine-written; a plain hyphen with spaces says the same.
  return (
    line
      .replace(LONG_DASH, " - ")
      // The term sheet calls itself a draft in its own text; the buyer receives a proposal, not a draft.
      .replace(/This\s+draft\s+proposes/g, "This term sheet proposes")
      .replace(/\(draft - unsigned\)/gi, "(unsigned)")
  );
}

function inline(line: string): string {
  return (
    line
      // Owner-only caveats the server puts in italics in brackets, e.g. *(wording not yet checked ...)*
      .replace(/\s*\*\([^)]*\)\*/g, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=$|[\s).,;:])/g, "$1$2")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
  );
}

function isTableRule(line: string): boolean {
  return /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-");
}

function tableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => inline(c.trim()));
}

export function toPlainMessage(markdown: string): string {
  const src = markdown.replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];
  let skipping = false;

  for (let i = 0; i < src.length; i++) {
    const raw = src[i];

    // Footer: a rule followed by the italic disclaimer ends the message.
    if (/^---+\s*$/.test(raw)) {
      const rest = src.slice(i + 1).join("\n").trim();
      if (rest === "" || /^\*?not legal advice/i.test(rest)) break;
      skipping = false;
      continue;
    }
    if (/^#{1,6}\s/.test(raw)) skipping = OWNER_ONLY.test(raw);
    if (skipping) continue;

    // Title line and the DRAFT banner block (blockquote lines).
    if (/^#\s/.test(raw) && out.length === 0) continue;
    if (/^\s*>/.test(raw)) continue;

    // Tables: "Label | value" rows become "Label: value" lines; the header row and rule go.
    if (/^\s*\|/.test(raw)) {
      if (isTableRule(raw)) continue;
      if (isTableRule(src[i + 1] ?? "")) continue; // the header row above a rule
      const cells = tableRow(raw).filter((c) => c !== "");
      out.push(dashes(cells.length === 2 ? `${cells[0]}: ${cells[1]}` : cells.join(", ")));
      continue;
    }

    // Headings become plain lines.
    const heading = /^#{2,6}\s+(.*)$/.exec(raw);
    out.push(dashes(inline(heading ? heading[1] : raw)));
  }

  return out
    .join("\n")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
