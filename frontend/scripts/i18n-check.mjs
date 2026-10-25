// Language-toggle check for the owner-facing MVP set (task F8).
//
// Runs without a browser and without the backend:
//   1. loads lib/i18n/en.ts and kn.ts through the TypeScript compiler,
//   2. proves every owner-facing card key has a Kannada string OR resolves to
//      its English source (the fallback contract), never blank and never a raw
//      key,
//   3. proves the MVP set (timeline summary, readiness headings, ladder stages,
//      eligibility pills, top four warnings) is actually translated,
//   4. checks placeholders survive translation and that the Buyer CFO view is
//      still English-only,
//   5. checks every Kannada string carries a // NEEDS-NATIVE-REVIEW marker.
//
// Usage:
//   node scripts/i18n-check.mjs           check (exit 1 on failure)
//   node scripts/i18n-check.mjs --doc     also write ../docs/kannada-review.md
//
// The visible half of the toggle test lives in scripts/smoke.mjs: it loads the
// running app with ?lang=kn and ?lang=en and checks the shell switches.

import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const FRONTEND = dirname(dirname(fileURLToPath(import.meta.url)));
const I18N = join(FRONTEND, "lib", "i18n");
const DOC_PATH = join(FRONTEND, "..", "docs", "kannada-review.md");
const WRITE_DOC = process.argv.includes("--doc");

const KANNADA = /[\u0c80-\u0cff]/;
const PLACEHOLDER = /\{(\w+)\}/g;

const failures = [];
const notes = [];

function fail(message) {
  failures.push(message);
}

function placeholders(value) {
  return [...new Set([...value.matchAll(PLACEHOLDER)].map((m) => m[1]))].sort();
}

async function loadTs(file, exportName) {
  const source = await readFile(join(I18N, file), "utf8");
  const out = ts.transpileModule(source, {
    fileName: file,
    reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  const syntax = (out.diagnostics ?? []).filter((d) => d.category === ts.DiagnosticCategory.Error);
  if (syntax.length) {
    const text = syntax.map((d) => ts.flattenDiagnosticMessageText(d.messageText, "\n")).join("; ");
    throw new Error(`${file} does not parse: ${text}`);
  }
  const url = `data:text/javascript;base64,${Buffer.from(out.outputText).toString("base64")}`;
  const mod = await import(url);
  return mod[exportName];
}

const en = await loadTs("en.ts", "en");
const kn = await loadTs("kn.ts", "kn");
const knWarnings = await loadTs("kn.ts", "knWarnings");
const knMvpKeys = await loadTs("kn.ts", "knMvpKeys");

const enKeys = Object.keys(en);
const knKeys = Object.keys(kn);

// ------------------------------------------------------------------ checks ----

// 1. No orphan keys: a Kannada key that English does not have can never render.
for (const key of knKeys) {
  if (!(key in en)) fail(`kn.${key} has no English source in en.ts`);
}

// 2. The MVP set must be present and in Kannada script.
for (const key of knMvpKeys) {
  if (!(key in en)) {
    fail(`MVP key ${key} is not in en.ts`);
    continue;
  }
  if (!kn[key]) {
    fail(`MVP key ${key} has no Kannada string (the owner-facing set must not fall back)`);
    continue;
  }
  if (!KANNADA.test(kn[key])) fail(`MVP key ${key} is not Kannada script: ${kn[key]}`);
}

// 3. Every Kannada string is non-empty and actually Kannada.
for (const key of knKeys) {
  if (!kn[key].trim()) fail(`kn.${key} is empty`);
  if (!KANNADA.test(kn[key])) fail(`kn.${key} contains no Kannada script: ${kn[key]}`);
}

// 4. Placeholders must match the English source exactly, or a number/date would
//    silently disappear.
for (const key of knKeys) {
  const expected = placeholders(en[key]);
  const actual = placeholders(kn[key]);
  if (expected.join(",") !== actual.join(",")) {
    fail(`kn.${key} placeholders {${actual.join("},{")}} do not match en {${expected.join("},{")}}`);
  }
}

// 5. Buyer CFO view stays English on purpose.
for (const key of knKeys) {
  if (key.startsWith("cfo.")) fail(`kn.${key} translates the Buyer CFO view, which must stay English`);
}

// 6. Warnings: four covered codes, placeholders equal to their documented vars.
for (const warning of knWarnings) {
  if (!KANNADA.test(warning.kn)) fail(`warning ${warning.code} is not Kannada script`);
  const actual = placeholders(warning.kn);
  const expected = [...warning.needsVars].sort();
  if (actual.join(",") !== expected.join(",")) {
    fail(`warning ${warning.code} placeholders {${actual.join("},{")}} do not match needsVars {${expected.join("},{")}}`);
  }
  for (const name of warning.needsVars) {
    if (!warning.en.includes(`{${name}}`)) fail(`warning ${warning.code} needs {${name}} but its English source has no such placeholder`);
  }
}

// 7. Every string is marked for native review.
const source = await readFile(join(I18N, "kn.ts"), "utf8");
const markers = (source.match(/\/\/ NEEDS-NATIVE-REVIEW/g) ?? []).length;
const strings = knKeys.length + knWarnings.length;
if (markers < strings) fail(`${strings} Kannada strings but only ${markers} // NEEDS-NATIVE-REVIEW markers`);

// 8. The fallback contract: every English key resolves to a non-empty string
//    under ?lang=kn. Missing Kannada is allowed, but must land on English.
let fallbacks = 0;
for (const key of enKeys) {
  if (!en[key].trim()) fail(`en.${key} is empty`);
  const resolved = kn[key] ?? en[key];
  if (!resolved || !resolved.trim()) fail(`key ${key} renders blank under ?lang=kn`);
  if (!(key in kn)) fallbacks += 1;
}

// 9. Owner-facing card coverage, per prefix, printed so the test is visible.
const CARD = {
  app: "Top bar / footer",
  nav: "Top bar / footer",
  conn: "Top bar / footer",
  banner: "Top bar / footer",
  footer: "Top bar / footer",
  lang: "Top bar / footer",
  state: "Shared states",
  common: "Shared states",
  badge: "Shared states",
  dues: "Dues list",
  tab: "Case tabs",
  case: "Case header",
  hero: "Claim hero",
  eligibility: "Eligibility pill / panel",
  stage: "Escalation ladder",
  ladder: "Escalation ladder",
  esc: "Escalation tab",
  gauge: "Evidence readiness card",
  readiness: "Evidence readiness card",
  timeline: "Timeline summary",
  tl: "Evidence timeline",
  send: "Send drawer",
};

const cards = new Map();
for (const key of enKeys) {
  const card = CARD[key.split(".")[0]] ?? "Other owner-facing copy";
  const row = cards.get(card) ?? { done: 0, total: 0 };
  row.total += 1;
  if (key in kn) row.done += 1;
  cards.set(card, row);
}

console.log("Kannada coverage by owner-facing card\n");
for (const [card, row] of [...cards].sort((a, b) => a[0].localeCompare(b[0]))) {
  const pct = Math.round((row.done / row.total) * 100);
  const state = row.done === row.total ? "KN" : "KN/EN";
  console.log(`  ${state.padEnd(6)} ${String(pct).padStart(3)}%  ${card.padEnd(30)} ${row.done}/${row.total}`);
}
console.log(`\n  ${knKeys.length} Kannada strings, ${fallbacks} English fallbacks, ${knWarnings.length} translated warnings, ${knMvpKeys.length} MVP keys.`);

if (notes.length) console.log(`\n${notes.join("\n")}`);

// ---------------------------------------------------------------------- doc ----

if (WRITE_DOC) {
  const phone = (key) => {
    const prefix = key.split(".")[0];
    if (["app", "nav", "conn", "banner", "footer", "lang"].includes(prefix)) return "Top bar / footer";
    if (["state", "common", "badge"].includes(prefix)) return "Shared states and badges";
    if (prefix === "dues") return "Dues list";
    if (prefix === "tab") return "Case tabs";
    if (prefix === "case") return "Case header";
    if (prefix === "hero") return "Claim hero";
    if (prefix === "eligibility") return "Eligibility pill / panel";
    if (prefix === "stage") return "Escalation ladder";
    if (prefix === "ladder") return "Escalation ladder";
    if (prefix === "send") return "Send drawer";
    if (prefix === "gauge" || prefix === "readiness") return "Evidence readiness card";
    if (prefix === "timeline") return "Timeline summary";
    return "Other owner-facing copy";
  };
  const mvp = new Set(knMvpKeys);
  const escapeCell = (value) => String(value).replace(/\|/g, "\\|");
  const row = (n, screen, key, english, kannada) =>
    `| ${n} | ${screen} | \`${key}\` | ${escapeCell(english)} | ${escapeCell(kannada)} | |`;

  const mvpRows = knMvpKeys.map((key, i) => row(i + 1, phone(key), key, en[key], kn[key]));
  const restKeys = knKeys.filter((key) => !mvp.has(key)).sort();
  const restRows = restKeys.map((key, i) => row(i + 1, phone(key), key, en[key], kn[key]));
  const warningRows = knWarnings.map(
    (w, i) => `| ${i + 1} | Assumptions drawer / send notes | \`${w.code}\` | ${escapeCell(w.en)} | ${escapeCell(w.kn)} | |`,
  );
  const cfoCount = enKeys.filter((key) => key.startsWith("cfo.")).length;

  const doc = `# Kannada review sheet

Status: **draft, not reviewed**. Every string below needs a native Kannada
speaker's check before it is shown to a real supplier. English is the source of
truth; the Kannada must not add a promise, a legal conclusion or a number the
English does not have.

Generated from \`frontend/lib/i18n/en.ts\` and \`frontend/lib/i18n/kn.ts\` by
\`npm run i18n:doc\`. Re-run after any string change; keep reviewer notes in a
separate copy or in the review issue, not in this generated file.

## How to review

1. Read the English source and the Kannada draft together. Flag anything that
   sounds like legal advice, a guarantee, or a stronger claim than the English.
2. Legal terms are deliberately kept in English in brackets, for example
   \`ಸಮಯ ಮಿತಿ (limitation)\`, \`ಬಡ್ಡಿ ಮನ್ನಾ (interest waiver)\`. Keep the bracket
   when you rewrite the sentence; do not invent a Kannada-only legal term.
3. \`{n}\`, \`{date}\`, \`{key}\`, \`{source}\` are placeholders filled by the engine.
   Leave them exactly as they are.
4. Mark each row **OK**, **fix** (write the replacement) or **ask** (the English
   itself is unclear).
5. The top four warnings use details read from the engine's English sentence
   (a constant name, a source ref, a date). If those details are missing, the UI
   shows the English sentence instead, so no fact is lost.

Screens covered by this sheet: the supplier workspace (case header, claim hero,
timeline summary, readiness card, escalation ladder, eligibility pill, warning
notes, send drawer) plus the shared shell. The **Buyer CFO view stays English**
by decision: its ${cfoCount} strings are not in \`kn.ts\`.

## A. Owner-facing MVP set (must be Kannada)

| # | Screen / card | Key | English source | Kannada draft | Reviewer |
|---|---|---|---|---|---|
${mvpRows.join("\n")}

## B. Other translated strings

These were drafted earlier for the demo shell. They already fall back to English
where a key is missing.

| # | Screen / card | Key | English source | Kannada draft | Reviewer |
|---|---|---|---|---|---|
${restRows.join("\n")}

## C. The top four engine warnings

Shown in the Assumptions drawer and in send-panel notes. The code is displayed
above the sentence; the English text below is the source these drafts translate.

| # | Screen / card | Code | English source | Kannada draft | Reviewer |
|---|---|---|---|---|---|
${warningRows.join("\n")}

## D. Deliberately English

- **Buyer CFO view** (\`cfo.*\`, ${cfoCount} strings): cost lines, settlement
  options and the unavailable state stay English.
- **Engine-provided text with no i18n key**: citations, assumption sentences,
  rule ids, statute references, party names, document kinds and any warning code
  outside section C are rendered as the backend sends them. That is a clean
  fallback, not a missing translation.
- **Numbers, dates and money** are never translated or re-typed; they arrive as
  placeholders or formatted by \`lib/format.ts\`.

## E. Sign-off

- [ ] Section A reviewed by a native speaker
- [ ] Section B reviewed by a native speaker
- [ ] Section C reviewed by a native speaker
- [ ] Legal terms still in English in brackets
- [ ] No string promises an outcome or gives legal advice
- [ ] \`npm run i18n:check\` passes
- [ ] \`npm run smoke\` language-toggle checks pass
`;

  await writeFile(DOC_PATH, doc, "utf8");
  console.log(`\nwrote ${DOC_PATH}`);
}

if (failures.length) {
  console.error(`\n${failures.length} language-toggle check(s) failed:`);
  for (const message of failures) console.error(`  FAIL ${message}`);
  process.exit(1);
}
console.log(`\nlanguage-toggle check ok: ${enKeys.length} English keys, ${knKeys.length} Kannada strings, no blank fallbacks.`);
