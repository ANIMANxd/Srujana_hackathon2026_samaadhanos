"""SamadhaanOS API scaffold.

Skeleton only: no routes beyond /api/v1/health, no legal logic, no statutory
values. The real endpoints (evaluate-case, presets, simulate-settlement,
generate-artifact, config, extract-evidence) arrive with the API prompt.
"""

from fastapi import FastAPI

app = FastAPI(
    title="SamadhaanOS API",
    version="0.0.0-scaffold",
    description="MSME payment-rights evaluation API. Contract v1.0 is frozen in architecture.md section 8.",
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness probe. Config load status is added once statute_config.json exists."""
    return {"status": "ok", "config_load": "not_loaded"}
