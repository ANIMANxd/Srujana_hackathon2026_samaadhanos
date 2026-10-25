# Dependencies

Golden rule 15: record every external library, API or dataset here as it is added.
The authoritative list of *installed* packages is `requirements.txt`; this file records
**why** each one is here and what it is not allowed to do.

## Added by the v4 store (backend/store/)

| Library | Version | Why it is here | Constraints |
|---|---|---|---|
| `sqlmodel` | `>=0.0.48` | ORM and table models for the v4 store (`backend/store/models.py`). Chosen because it keeps one Pydantic model per table, so the store's rows and the contract models stay in the same idiom. | Money columns are `TEXT` through `DecimalText`, never `REAL`. The schema must stay Postgres-compatible. The engine stays stateless: the store persists engine input and output, it never computes a legal number. |
| `sqlalchemy` | 2.x (transitive, via `sqlmodel`) | Engine, sessions, the partial unique index on `tracks`. | Not imported directly outside `backend/store/`. |

## Present before the v4 work

Recorded here from the comments in `requirements.txt`. These entries are **not** a
provenance audit — they were backfilled when this file was created, and the commit that
introduced each one owns the real justification.

| Library | Version | Why it is here |
|---|---|---|
| `fastapi` | `>=0.115` | The API itself (contract v1.0, `backend/app/main.py`). |
| `pydantic` | `>=2.9` | Contract models and validation. |
| `uvicorn` | `>=0.30` | ASGI server for `make backend` / `make dev`. |
| `python-dateutil` | `>=2.9` | Month stepping with end-of-month clamping in the engine. |
| `pytest` | `>=8.3` | Test runner for `backend/tests/{dev,spec,contract}`. |
| `python-multipart` | `>=0.0.9` | Multipart uploads for `POST /api/v1/extract-evidence`. |
| `jsonschema` | `>=4.18` | OpenAPI conformance tests validate real responses against `contracts/openapi.json`. |
| `reportlab` | `>=4.0` | PDF rendering for `/generate-artifact`. Degrades to markdown when missing. |

`openapi-typescript` (via `npx`) generates `contracts/types.ts`. It is a build-time tool
only; `backend/app/export_types.py` falls back to a built-in generator when Node is absent,
so the build never depends on the network.

## Not added, on purpose

- **No ORM beyond SQLModel.** No Alembic yet: `make db-reset` recreates the SQLite demo
  database from the models. Migrations become necessary the first time demo data must
  survive a schema change.
- **No Aadhaar / KYC library, ever.** The demo eSign accepts a test OTP only; no Aadhaar
  number is collected, stored or logged (golden rule 18).
- **No real eSign, TReDS or bank SDK.** Mocks are local services with fictional parties
  (golden rules 16-17). Any real provider is described as "would integrate with".
