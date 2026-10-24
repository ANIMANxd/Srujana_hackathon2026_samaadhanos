"""Generate contract fixtures from the live models and the live engine.

Run: python -m backend.app.export_fixtures   (or `make contract-fixtures`)

Writes contracts/fixtures/<preset>.request.json (the preset's input, re-validated
through the model) and <preset>.response.json — **the engine's own evaluation of
that input**. Nothing is hand-typed: the request comes from the preset file and
the response is whatever POST /evaluate-case returns for it, so a fixture can
never drift from the API and every figure in it traces back to the engine
(golden rule 7 and 12).

A preset that cannot be evaluated stops the export with the engine's own plain
English error rather than writing a fixture, because a fixture is a recorded
answer: writing one for a case that does not evaluate would freeze a lie.
"""

import json
from pathlib import Path

from backend.app.config_loader import load_config
from backend.app.main import PRESETS_DIR, _read_json
from backend.app.schemas import CaseEvaluationRequest
from backend.engine.config import StatuteConfig
from backend.engine.evaluate import evaluate_case

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"


def _dump(model) -> str:
    return json.dumps(model.model_dump(mode="json", by_alias=True), indent=2) + "\n"


def export() -> list[str]:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    config = StatuteConfig.from_dict(load_config())
    written = []
    for preset in sorted(PRESETS_DIR.glob("*.json")):
        data = _read_json(preset)
        request = CaseEvaluationRequest.model_validate(data.get("request", data))
        response = evaluate_case(config, request)
        (FIXTURES / f"{preset.stem}.request.json").write_text(_dump(request), encoding="utf-8")
        (FIXTURES / f"{preset.stem}.response.json").write_text(_dump(response), encoding="utf-8")
        written.append(preset.stem)
    return written


if __name__ == "__main__":
    for stem in export():
        print(f"wrote {stem}.request.json + {stem}.response.json")
