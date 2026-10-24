"""Generate contract fixtures from the live models (golden rule 7/12).

Run: python -m backend.app.export_fixtures

Writes contracts/fixtures/<preset>.request.json (the preset's input, re-validated
through the model) and <preset>.response.json (the placeholder evaluation the API
returns for that request). The response is produced by calling the same code path
the API uses, so no number here is hand-typed — they are PLACEHOLDER constants
from backend/app/placeholder.py, labelled as such in warnings[].
"""

import json
from pathlib import Path

from backend.app.main import PRESETS_DIR, _read_json
from backend.app.placeholder import placeholder_evaluation
from backend.app.schemas import CaseEvaluationRequest

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"


def _dump(model) -> str:
    return json.dumps(model.model_dump(mode="json", by_alias=True), indent=2) + "\n"


def export() -> list[str]:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    written = []
    for preset in sorted(PRESETS_DIR.glob("*.json")):
        data = _read_json(preset)
        request = CaseEvaluationRequest.model_validate(data.get("request", data))
        response = placeholder_evaluation(request)
        (FIXTURES / f"{preset.stem}.request.json").write_text(_dump(request), encoding="utf-8")
        (FIXTURES / f"{preset.stem}.response.json").write_text(_dump(response), encoding="utf-8")
        written.append(preset.stem)
    return written


if __name__ == "__main__":
    for stem in export():
        print(f"wrote {stem}.request.json + {stem}.response.json")
