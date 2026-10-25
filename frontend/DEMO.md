# 60-second demo script

One pass, four screens. The on-screen hint strip follows this order and is the
only thing `?demo=1` adds; it never edits a request or computes a figure.

## Run it

```bash
cd frontend
npm run dev
```

Open **http://localhost:3000/?demo=1**. That redirects to CASE-01. Every link
keeps `demo=1`, so the hint strip stays with the recording.

The backend is optional:

- **Backend off** — preset screens render the engine output saved in
  `contracts/fixtures/` and the top bar says **Offline**. The script still runs.
- **Backend on** (`make backend` in the repo root) — the same screens use live
  engine output and the top bar says **Engine live**.

`?judge=1` re-opens the judge console inside demo mode; it is hidden by default.

## The pass

| Time | Screen | URL | Point at |
|---|---|---|---|
| 0:00–0:15 | CASE-01 · Supplier view | `/case/case_01?demo=1` | Total claim, the statutory timeline, and the one recommended next step |
| 0:15–0:30 | CASE-01 · Buyer CFO | `/case/case_01?demo=1&view=cfo` | Three separate cost lines; say out loud that they are never added together |
| 0:30–0:45 | CASE-02 · Objection resolved | `/case/case_02?demo=1` | The day-9 written objection; acceptance starts when it was resolved |
| 0:45–1:00 | CASE-05 · Blocked at the gate | `/case/case_05a?demo=1` | The gate explains why the Act route is unavailable; no claim and no zero |

Press **Next** in the hint strip between screens, or follow the table. The last
step offers **Restart the demo**.

## Recording setup

- Record at **1920×1080**, browser at **100% zoom**, full screen.
- The layout is tuned for 1080p: one step larger type from 1280px up, a 1200px
  content column, and no table smaller than 15px.
- Keep the hint strip visible; it is small and fixed to the bottom edge, so it
  never shifts the page.
- Let CASE-01 settle for a second before speaking. With a slow backend the
  skeleton holds the hero, timeline and card shapes.

## Checks before recording

```bash
cd frontend
npm run i18n:check   # language coverage and fallbacks
npm run dev          # in another terminal
npm run smoke        # 200s, demo sequence, fixtures current, language toggle
```

`npm run smoke` verifies the four demo fixtures exist, are byte-identical to
`contracts/fixtures/`, and carry no `PLACEHOLDER_DATA`, so the placeholder
banner cannot appear when fixtures are current.
