// Route smoke test: requests every screen on a running server and checks for
// HTTP 200 and no framework error markers. Usage:
//   npm run dev   (or npm start)   then   npm run smoke
// Optional: SMOKE_BASE=http://127.0.0.1:3000

import { existsSync, readFileSync } from "node:fs";

const BASE = process.env.SMOKE_BASE ?? "http://127.0.0.1:3000";

const ROUTES = [
  "/",
  "/?dues=invoices",
  "/customers/review",
  "/import",
  "/customers/01JAV5CST0000000000000001",
  "/?view=cfo",
  "/upload",
  "/case/case_01",
  "/case/case_01?view=cfo",
  "/case/case_01?judge=1",
  "/case/case_01/pack",
  "/case/case_01/send/1",
  "/case/case_01/send/2",
  "/case/case_01/send/3",
  "/case/case_01/send/4",
  "/eligibility/case_01",
  "/case/case_01?send=2",
  "/case/case_06",
  "/case/case_04?tab=evidence",
  "/case/case_06?tab=evidence",
  "/case/case_04?tab=math",
  "/case/case_05a?view=cfo",
  "/case/case_01?tab=escalation&step=4",
  "/case/case_05a?tab=escalation",
  "/case/case_06?tab=escalation&step=4",
  "/eligibility/case_05a",
  "/case/does_not_exist",
  // Language toggle routes: the shell must switch language, and cards must
  // either translate or fall back to English (never blank). See below.
  "/?lang=kn",
  "/?lang=en",
  "/upload?lang=kn",
  "/case/case_01?lang=kn",
  "/case/case_01?lang=kn&tab=evidence",
  "/case/case_01?lang=kn&tab=escalation",
  "/case/case_01?view=cfo&lang=kn",
  "/case/case_05a?lang=kn&tab=evidence",
  // Demo mode: the scripted sequence must load without the judge clutter.
  "/?demo=1",
  "/case/case_01?demo=1",
  "/case/case_01?demo=1&view=cfo",
  "/case/case_02?demo=1",
  "/case/case_05a?demo=1",
  "/case/case_01?demo=1&judge=1",
];

const ERROR_MARKERS = ["Application error", "Unhandled Runtime Error", "Internal Server Error", "__next_error__"];

let failed = 0;
for (const route of ROUTES) {
  try {
    const res = await fetch(BASE + route);
    const html = await res.text();
    const marker = ERROR_MARKERS.find((m) => html.includes(m));
    if (res.status !== 200 || marker) {
      failed++;
      console.log(`FAIL ${res.status} ${route}${marker ? ` (${marker})` : ""}`);
    } else {
      console.log(`ok   ${res.status} ${route}`);
    }
  } catch (e) {
    failed++;
    console.log(`FAIL ---  ${route} (${e instanceof Error ? e.message : String(e)})`);
  }
}

// The API proxy must answer: 200 when the backend is up, or a 5xx when it is down
// (the client then falls back to fixtures). Report which, without failing.
try {
  const res = await fetch(`${BASE}/api/v1/health`);
  console.log(`info api proxy /api/v1/health -> ${res.status} (${res.ok ? "backend up" : "backend down: offline mode"})`);
} catch (e) {
  console.log(`info api proxy unreachable (${e instanceof Error ? e.message : String(e)})`);
}

// ---------------------------------------------------------- demo mode ----
// Acceptance guard: the four scripted screens need current, engine-generated
// fixtures and must not carry PLACEHOLDER_DATA (that is the only banner the
// acceptance forbids). Then the hint sequence and the hidden judge clutter.
try {
  const demoIds = ["case_01", "case_02", "case_05a"];
  for (const id of demoIds) {
    for (const kind of ["request", "response"]) {
      const front = new URL(`../fixtures/${id}.${kind}.json`, import.meta.url);
      const contract = new URL(`../../contracts/fixtures/${id}.${kind}.json`, import.meta.url);
      if (!existsSync(front) || !existsSync(contract)) {
        failed++;
        console.log(`FAIL demo fixture missing: ${id}.${kind}.json`);
        continue;
      }
      if (!readFileSync(front).equals(readFileSync(contract))) {
        failed++;
        console.log(`FAIL demo fixture stale: frontend/fixtures/${id}.${kind}.json differs from contracts/fixtures`);
      }
    }
    const response = JSON.parse(readFileSync(new URL(`../fixtures/${id}.response.json`, import.meta.url), "utf8"));
    if (response.warnings?.some((w) => w.code === "PLACEHOLDER_DATA")) {
      failed++;
      console.log(`FAIL demo fixture ${id} carries PLACEHOLDER_DATA`);
    }
  }

  const html = async (path) => (await fetch(BASE + path)).text();
  const start = await fetch(BASE + "/?demo=1");
  const startHtml = await start.text();
  const finalUrl = new URL(start.url);
  const step1 = await html("/case/case_01?demo=1");
  const step2 = await html("/case/case_01?demo=1&view=cfo");
  const step3 = await html("/case/case_02?demo=1");
  const step4 = await html("/case/case_05a?demo=1");
  const judge = await html("/case/case_01?demo=1&judge=1");

  const checks = [
    ["starts on CASE-01", finalUrl.pathname === "/case/case_01" && finalUrl.searchParams.get("demo") === "1" && startHtml.includes("1 of 4")],
    ["step 1 hint", step1.includes("1 of 4") && step1.includes("Supplier view")],
    ["step 1 next link keeps demo and asks for CFO", step1.includes("demo=1") && step1.includes("view=cfo")],
    ["step 1 hides the judge button", !step1.includes("Judge console")],
    ["explicit ?judge=1 still opens the console", judge.includes("Judge console")],
    ["step 2 hint", step2.includes("2 of 4") && step2.includes("Buyer CFO")],
    ["step 3 hint", step3.includes("3 of 4") && step3.includes("Objection resolved")],
    ["step 4 hint", step4.includes("4 of 4") && step4.includes("Blocked at the gate")],
    ["step 4 offers a restart", step4.includes("Restart the demo")],
    ["no placeholder banner copy", !(step1 + step2 + step3 + step4).includes("Placeholder data")],
  ];

  // Follow the visible Next links from the first screen to the last: proves the
  // 60-second sequence runs in one pass without typing a URL.
  const nextHref = (page) => {
    const tag = /<a[^>]*data-demo-next[^>]*>/.exec(page)?.[0] ?? "";
    return /href="([^"]+)"/.exec(tag)?.[1]?.replaceAll("&amp;", "&") ?? null;
  };
  const walked = [];
  let page = startHtml;
  for (let i = 0; i < 3; i++) {
    const href = nextHref(page);
    if (!href) break;
    const res = await fetch(BASE + href);
    page = await res.text();
    const at = new URL(res.url);
    walked.push(`${at.pathname}${at.search}`);
  }
  checks.push(
    ["one-pass link chain reaches four screens", walked.length === 3],
    ["chain: step 2 is Buyer CFO", walked[0] === "/case/case_01?view=cfo&demo=1"],
    ["chain: step 3 is CASE-02", walked[1] === "/case/case_02?demo=1"],
    ["chain: step 4 is CASE-05", walked[2] === "/case/case_05a?demo=1"],
    ["chain ends on a restart hint", page.includes("Restart the demo")],
  );
  for (const [label, ok] of checks) {
    if (ok) console.log(`ok   demo ${label}`);
    else {
      failed++;
      console.log(`FAIL demo ${label}`);
    }
  }
} catch (e) {
  failed++;
  console.log(`FAIL demo checks (${e instanceof Error ? e.message : String(e)})`);
}

// ------------------------------------------------- language toggle test ----
// Visible half of the i18n check (the dictionary half is `npm run i18n:check`).
// The shell is server-rendered, so it proves the toggle really switches what a
// user sees. Card copy that is not translated must land on English, not blank
// and not a raw key. Buyer CFO copy is checked by the dictionary test, which
// forbids `cfo.*` keys in kn.ts.
try {
  const html = async (path) => (await fetch(BASE + path)).text();
  const knHome = await html("/?lang=kn");
  const enHome = await html("/?lang=en");
  const knUpload = await html("/upload?lang=kn");

  const checks = [
    ["kn shell: nav is Kannada", knHome.includes("ಬಾಕಿಗಳು")],
    ["kn shell: language group is Kannada", knHome.includes("ಭಾಷೆ")],
    ["kn shell: footer is Kannada", knHome.includes("ಕಾನೂನು ಸಲಹೆ ಅಲ್ಲ")],
    ["kn shell: toggle keeps Kannada selected", knHome.includes("lang=kn")],
    ["kn shell: toggle offers the English label", knHome.includes("English")],
    ["en shell: toggle links to Kannada", enHome.includes("lang=kn")],
    ["en shell: nav is English", enHome.includes(">Dues<")],
    ["en shell: no Kannada nav label", !enHome.includes("ಬಾಕಿಗಳು")],
    ["kn page: untranslated card copy falls back to English", knUpload.includes("Add an invoice")],
    ["kn page: shell around the fallback is still Kannada", knUpload.includes("ಬಾಕಿಗಳು")],
    ["kn page: raw key names are never rendered", !/nav\.dues|stage\.1\.title|gauge\.title/.test(knHome + knUpload)],
  ];

  for (const [label, ok] of checks) {
    if (ok) console.log(`ok   lang ${label}`);
    else {
      failed++;
      console.log(`FAIL lang ${label}`);
    }
  }
} catch (e) {
  failed++;
  console.log(`FAIL lang toggle checks (${e instanceof Error ? e.message : String(e)})`);
}

if (failed) {
  console.log(`\n${failed} route(s) failed`);
  process.exit(1);
}
console.log(`\nall ${ROUTES.length} routes ok, demo checks ok, language toggle checks ok`);
