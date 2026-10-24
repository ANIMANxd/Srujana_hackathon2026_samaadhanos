"""Export the OpenAPI contract to contracts/openapi.json (section 9.1).

Run: python -m backend.app.export_openapi
This is the source of truth for contracts/types.ts. The contract-test suite
asserts that the committed openapi.json matches the live app, so drift fails
loudly (make test).
"""

import json
from pathlib import Path

from backend.app.main import app

OUT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


def export() -> Path:
    spec = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    path = export()
    print(f"wrote {path}")
