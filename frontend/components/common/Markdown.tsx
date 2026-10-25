import { Fragment, type ReactNode } from "react";

/**
 * Minimal markdown for the backend's draft artifacts: headings, quotes, lists
 * (with [ ] / [x] tasks), tables, rules, paragraphs, and **bold** / *italic* /
 * `code` inline. Everything is rendered as React text nodes, never as HTML, so
 * a draft cannot inject markup.
 */

type Block =
  | { kind: "h"; level: number; text: string }
  | { kind: "p"; text: string }
  | { kind: "quote"; lines: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "hr" };

const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const isSeparator = (l: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
const cells = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i++;
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      out.push({ kind: "h", level: h[1].length, text: h[2] });
      i++;
      continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      out.push({ kind: "hr" });
      i++;
      continue;
    }
    if (isTableRow(line) && i + 1 < lines.length && isSeparator(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
      out.push({ kind: "table", head, rows });
      continue;
    }
    if (/^\s*>/.test(line)) {
      const q: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push({ kind: "quote", lines: q });
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      out.push({ kind: "ul", items });
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      out.push({ kind: "ol", items });
      continue;
    }
    const para: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,4}\s|\s*>|\s*[-*]\s+|\s*\d+[.)]\s+|\s*\|)/.test(lines[i])
    ) {
      para.push(lines[i++]);
    }
    out.push({ kind: "p", text: para.join(" ") });
  }
  return out;
}

function inline(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) return <strong key={i} className="font-semibold text-ink-950">{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`") && p.length > 2) return <code key={i} className="num rounded bg-paper-sunk px-1 text-[0.85em]">{p.slice(1, -1)}</code>;
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>;
    return <Fragment key={i}>{p}</Fragment>;
  });
}

function Item({ text }: { text: string }) {
  const task = /^\[( |x|X)\]\s+(.*)$/.exec(text);
  if (!task) return <>{inline(text)}</>;
  const done = task[1] !== " ";
  return (
    <span className="flex items-start gap-2">
      <span aria-hidden="true" className={`mt-1 grid h-3.5 w-3.5 shrink-0 place-items-center rounded-[3px] border ${done ? "border-ok bg-ok text-white" : "border-ink-300"}`}>
        {done && <span className="text-[9px] leading-none">✓</span>}
      </span>
      <span className="sr-only">{done ? "[x]" : "[ ]"}</span>
      <span>{inline(task[2])}</span>
    </span>
  );
}

export function Markdown({ source, className = "" }: { source: string; className?: string }) {
  const blocks = parse(source);
  return (
    <div className={`flex flex-col gap-3 text-sm leading-relaxed text-ink-800 ${className}`}>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "h":
            return b.level === 1 ? (
              <h3 key={i} className="text-base font-semibold tracking-[-0.01em] text-ink-950">{inline(b.text)}</h3>
            ) : (
              <h4 key={i} className="mt-2 text-sm font-semibold text-ink-950">{inline(b.text)}</h4>
            );
          case "hr":
            return <hr key={i} className="border-rule" />;
          case "quote":
            return (
              <blockquote key={i} className="flex flex-col gap-1 rounded-md border-l-2 border-saffron-500 bg-paper px-3 py-2 text-ink-700">
                {b.lines.map((l, j) => (
                  <p key={j}>{inline(l)}</p>
                ))}
              </blockquote>
            );
          case "ul":
            return (
              <ul key={i} className="flex flex-col gap-1.5">
                {b.items.map((it, j) => (
                  <li key={j} className={/^\[( |x|X)\]/.test(it) ? "" : "ml-4 list-disc"}>
                    <Item text={it} />
                  </li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={i} className="ml-5 flex list-decimal flex-col gap-1.5">
                {b.items.map((it, j) => (
                  <li key={j}>{inline(it)}</li>
                ))}
              </ol>
            );
          case "table":
            return (
              <div key={i} className="overflow-x-auto rounded-lg border border-rule">
                <table className="w-full border-collapse text-xs">
                  <thead className="border-b border-rule bg-paper text-left text-ink-500">
                    <tr>
                      {b.head.map((c, j) => (
                        <th key={j} scope="col" className="px-3 py-2 font-medium">{inline(c)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j} className="border-t border-rule align-top">
                        {r.map((c, k) => (
                          <td key={k} className="px-3 py-2 text-ink-800">{inline(c)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return <p key={i}>{inline(b.text)}</p>;
        }
      })}
    </div>
  );
}
