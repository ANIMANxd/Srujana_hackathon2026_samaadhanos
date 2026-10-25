// Route smoke test: requests every screen on a running server and checks for
// HTTP 200 and no framework error markers. Usage:
//   npm run dev   (or npm start)   then   npm run smoke
// Optional: SMOKE_BASE=http://127.0.0.1:3000

const BASE = process.env.SMOKE_BASE ?? "http://127.0.0.1:3000";

const ROUTES = [
  "/",
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
  "/eligibility/case_05a",
  "/case/does_not_exist",
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

if (failed) {
  console.log(`\n${failed} route(s) failed`);
  process.exit(1);
}
console.log(`\nall ${ROUTES.length} routes ok`);
