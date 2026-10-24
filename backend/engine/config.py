"""config.py — typed loader and lookup helpers for statute_config.json.

Pure per section 6: no file I/O, no clock, no network, no globals. The parsed
config dict is passed in explicitly, so the engine stays deterministic and the
API decides where the bytes come from (backend/app/config_loader.py owns the file).

Every statutory value in the config carries {value, source_ref, verified, note}.
Any constant a computation actually uses that is unverified or null produces an
UNVERIFIED_CONSTANT warning (section 5). Usage is tracked as the lookups run, so
a value nobody touched never clutters the output. Call strict_check() at the end
of a computation to turn those warnings into errors (STRICT_VERIFIED=1).

This module holds data and lookups only. No rule logic, no dates arithmetic
beyond "which epoch covers this day".
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

# Keys the loader fails fast on if absent (section 5). gated_features is an
# object, so it is checked by shape rather than by enum membership.
REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "interest_multiplier",
        "objection_window_days",
        "credit_cap_days",
        "no_agreement_days",
        "bank_rate_epochs",
        "size_epochs",
        "silpi_test_date",
        "trader_nic_prefixes",
        "limitation_years",
        "section_43bh_first_fy",
        "rate_mode_default",
        "appropriation_mode_default",
        "payment_boundary_convention",
        "day_count_fraction_days",
        "tax_presets",
        "gated_features",
    }
)

GATED_FEATURE_NAMES: frozenset[str] = frozenset(
    {"gst_itc_180d", "msme1_return", "s19_deposit"}
)

# Codes that appear in engine output. Plain, uppercase, stable for the UI.
WARNING_UNVERIFIED_CONSTANT = "UNVERIFIED_CONSTANT"


class ConfigError(Exception):
    """The config dict is structurally unusable. Fail fast, do not guess (section 6)."""


class NoEpochFound(ConfigError):
    """No bank-rate or size epoch covers the requested date.

    Raised rather than guessed, because inventing a rate would be inventing law
    (golden rule 1). The caller should surface this as INSUFFICIENT_DATA.
    """


class StrictVerificationError(ConfigError):
    """STRICT_VERIFIED is on and an unverified constant was used (section 5)."""


# ---------------------------------------------------------------- warnings ----


@dataclass(frozen=True)
class Warning:
    """One UNVERIFIED_CONSTANT entry, shaped like the contract's warnings[] block."""

    code: str
    severity: str  # INFO | WARN | BLOCK, per the contract WarningSeverity enum
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "text": self.text}


# ------------------------------------------------------------- typed views ----


@dataclass(frozen=True)
class BankRateEpoch:
    """One Bank Rate period. `from` is the first day the rate applies."""

    from_date: date | None
    bank_rate_pct: Decimal


@dataclass(frozen=True)
class SizeLimits:
    investment_cr: Decimal
    turnover_cr: Decimal


@dataclass(frozen=True)
class SizeEpoch:
    """Investment/turnover ceilings in force from `from_date`.

    A None from_date is the indefinitely-early fallback (see the size_epochs note
    in the config: the earlier set is named but undated in section 5).
    """

    from_date: date | None
    micro: SizeLimits
    small: SizeLimits
    medium: SizeLimits


@dataclass(frozen=True)
class TaxPreset:
    id: str
    label: str
    tax_rate_pct: Decimal


@dataclass(frozen=True)
class ConfigEntry:
    """One config entry as stored: value, source, verified flag, note (section 5)."""

    value: Any
    source_ref: str
    verified: bool
    note: str


# ------------------------------------------------------------------ loader ----


def _parse_date(raw: Any, *, context: str) -> date | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ConfigError(f"{context}: date must be a string or null, got {type(raw).__name__}")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(f"{context}: {raw!r} is not an ISO YYYY-MM-DD date") from exc


def _decimal(raw: Any, *, context: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise ConfigError(f"{context}: expected a decimal string or int, got {type(raw).__name__}")
    try:
        return Decimal(str(raw))
    except Exception as exc:  # noqa: BLE001 - Decimal raises several types
        raise ConfigError(f"{context}: {raw!r} is not a valid decimal") from exc


def _require_entry(key: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError(f"config key {key!r} must be an object with value/source_ref/verified/note")
    for field_name in ("value", "source_ref", "verified", "note"):
        if field_name not in raw:
            raise ConfigError(f"config key {key!r} is missing the {field_name!r} field")
    if not isinstance(raw["verified"], bool):
        raise ConfigError(f"config key {key!r}: verified must be a boolean")
    return raw


def _sorted_epochs(raw: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ConfigError(f"config key {key!r} must be a list of epochs")
    for index, epoch in enumerate(raw):
        if not isinstance(epoch, dict):
            raise ConfigError(f"config key {key!r}[{index}] must be an object")
        if "from" not in epoch:
            raise ConfigError(f"config key {key!r}[{index}] is missing 'from'")
    return raw


class StatuteConfig:
    """A validated, typed view over the statute config.

    Construct with from_dict(), which fails fast on missing or malformed keys.
    Lookups record which constants they used, so warnings() reflects what a
    computation actually relied on rather than every unverified value in the file.
    """

    def __init__(self, entries: dict[str, dict[str, Any]]):
        self._entries = entries
        self._used: set[str] = set()
        self._bank_rate_epochs = self._load_bank_rate_epochs()
        self._size_epochs = self._load_size_epochs()
        self._tax_presets = self._load_tax_presets()

    # -- construction -------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Any) -> "StatuteConfig":
        """Validate the raw dict and build a StatuteConfig, or raise ConfigError."""
        if not isinstance(data, dict):
            raise ConfigError("statute config must be a JSON object")

        entries: dict[str, dict[str, Any]] = {}
        for key in REQUIRED_KEYS:
            if key not in data:
                raise ConfigError(f"statute config is missing required key {key!r}")
            entries[key] = _require_entry(key, data[key])

        gated = entries["gated_features"]["value"]
        if not isinstance(gated, dict):
            raise ConfigError("config key 'gated_features' value must be an object")
        unknown = set(gated) - GATED_FEATURE_NAMES
        if unknown:
            raise ConfigError(f"gated_features has unknown names: {sorted(unknown)}")

        return cls(entries)

    # -- typed loaders ------------------------------------------------------

    def _load_bank_rate_epochs(self) -> list[BankRateEpoch]:
        raw = _sorted_epochs(self._entries["bank_rate_epochs"]["value"], "bank_rate_epochs")
        epochs = [
            BankRateEpoch(
                from_date=_parse_date(e.get("from"), context="bank_rate_epochs.from"),
                bank_rate_pct=_decimal(e.get("bank_rate_pct"), context="bank_rate_epochs.bank_rate_pct"),
            )
            for e in raw
        ]
        return self._order_ascending(epochs, "bank_rate_epochs")

    def _load_size_epochs(self) -> list[SizeEpoch]:
        raw = _sorted_epochs(self._entries["size_epochs"]["value"], "size_epochs")
        epochs: list[SizeEpoch] = []
        for index, e in enumerate(raw):
            ctx = f"size_epochs[{index}]"
            bands: dict[str, SizeLimits] = {}
            for band in ("micro", "small", "medium"):
                band_raw = e.get(band)
                if not isinstance(band_raw, dict):
                    raise ConfigError(f"{ctx}.{band} must be an object with investment_cr/turnover_cr")
                bands[band] = SizeLimits(
                    investment_cr=_decimal(band_raw.get("investment_cr"), context=f"{ctx}.{band}.investment_cr"),
                    turnover_cr=_decimal(band_raw.get("turnover_cr"), context=f"{ctx}.{band}.turnover_cr"),
                )
            epochs.append(
                SizeEpoch(
                    from_date=_parse_date(e.get("from"), context=f"{ctx}.from"),
                    micro=bands["micro"],
                    small=bands["small"],
                    medium=bands["medium"],
                )
            )
        return self._order_ascending(epochs, "size_epochs")

    def _load_tax_presets(self) -> list[TaxPreset]:
        raw = self._entries["tax_presets"]["value"]
        if not isinstance(raw, list):
            raise ConfigError("config key 'tax_presets' must be a list")
        presets = [
            TaxPreset(
                id=str(p.get("id")),
                label=str(p.get("label")),
                tax_rate_pct=_decimal(p.get("tax_rate_pct"), context=f"tax_presets[{i}].tax_rate_pct"),
            )
            for i, p in enumerate(raw)
            if isinstance(p, dict)
        ]
        if len(presets) != len(raw):
            raise ConfigError("config key 'tax_presets' entries must be objects")
        return presets

    @staticmethod
    def _order_ascending(epochs: Iterable[Any], key: str) -> list[Any]:
        """Sort epochs by date, undated (fallback) first, and reject ties."""
        items = list(epochs)
        items.sort(key=lambda e: (e.from_date is not None, e.from_date or date.min))
        previous: date | None = None
        for epoch in items:
            if epoch.from_date is not None and epoch.from_date == previous:
                raise ConfigError(f"config key {key!r} has two epochs starting on {epoch.from_date}")
            previous = epoch.from_date
        return items

    # -- usage tracking -----------------------------------------------------

    def _mark_used(self, key: str) -> None:
        self._used.add(key)

    @property
    def used_keys(self) -> frozenset[str]:
        """Keys a lookup has relied on so far."""
        return frozenset(self._used)

    def reset_usage(self) -> None:
        """Forget recorded usage, e.g. between two evaluated cases."""
        self._used.clear()

    def warnings(self) -> list[Warning]:
        """One UNVERIFIED_CONSTANT per used key that is unverified or null."""
        out: list[Warning] = []
        for key in sorted(self._used):
            entry = self._entries[key]
            if entry["verified"] and entry["value"] is not None:
                continue
            reason = "is null" if entry["value"] is None else "is not verified against the statute sheet"
            out.append(
                Warning(
                    code=WARNING_UNVERIFIED_CONSTANT,
                    severity="WARN",
                    text=(
                        f"Constant {key!r} {reason} (source {entry['source_ref']!r}). "
                        "Treat any number that depends on it as provisional until the "
                        "statute sheet is captured."
                    ),
                )
            )
        return out

    def strict_check(self) -> None:
        """Raise if any used constant is unverified or null.

        Call at the end of a computation when STRICT_VERIFIED is on (section 5),
        so no unverified statutory number reaches the demo video.
        """
        unverified = [w for w in self.warnings()]
        if unverified:
            keys = ", ".join(sorted(self._used))
            raise StrictVerificationError(
                "STRICT_VERIFIED is on and these used constants are unverified or null: " + keys
            )

    # -- entry access -------------------------------------------------------

    def _require_value(self, key: str) -> Any:
        if key not in self._entries:
            raise ConfigError(f"statute config is missing required key {key!r}")
        self._mark_used(key)
        return self._entries[key]["value"]

    def interest_multiplier(self) -> Decimal:
        value = self._require_value("interest_multiplier")
        if value is None:
            # Null is legal in the file; the caller decides how to degrade.
            return Decimal("0")
        return Decimal(str(value))

    def objection_window_days(self) -> int | None:
        value = self._require_value("objection_window_days")
        return None if value is None else int(value)

    def credit_cap_days(self) -> int | None:
        value = self._require_value("credit_cap_days")
        return None if value is None else int(value)

    def no_agreement_days(self) -> int | None:
        value = self._require_value("no_agreement_days")
        return None if value is None else int(value)

    def day_count_fraction_days(self) -> int | None:
        value = self._require_value("day_count_fraction_days")
        return None if value is None else int(value)

    def trader_nic_prefixes(self) -> list[str]:
        value = self._require_value("trader_nic_prefixes") or []
        return [str(v) for v in value]

    def rate_mode_default(self) -> str | None:
        return self._require_value("rate_mode_default")

    def appropriation_mode_default(self) -> str | None:
        return self._require_value("appropriation_mode_default")

    def payment_boundary_convention(self) -> str | None:
        return self._require_value("payment_boundary_convention")

    def entry(self, key: str) -> ConfigEntry:
        """The full {value, source_ref, verified, note} entry for `key`.

        Marks the key as used, so a citation built from it also puts the key in
        the UNVERIFIED_CONSTANT warnings. Use this when a rule reads a constant
        to cite it, not just to compute with it.
        """
        if key not in self._entries:
            raise ConfigError(f"statute config is missing required key {key!r}")
        self._mark_used(key)
        return ConfigEntry(**self._entries[key])

    def silpi_test_date(self) -> str | None:
        return self._require_value("silpi_test_date")

    def limitation_years(self) -> int | None:
        value = self._require_value("limitation_years")
        return None if value is None else int(value)

    def section_43bh_first_fy(self) -> str | None:
        return self._require_value("section_43bh_first_fy")

    def gated_features(self) -> dict[str, bool]:
        value = self._require_value("gated_features") or {}
        return {name: bool(value.get(name, False)) for name in GATED_FEATURE_NAMES}

    # -- lookups ------------------------------------------------------------

    def bank_rate_on(self, day: date) -> Decimal:
        """Bank Rate in force on `day`, as a percentage.

        Picks the latest epoch whose start is on or before `day`. Raises
        NoEpochFound when no epoch covers the day, because guessing a rate would
        be inventing law (golden rule 1).
        """
        self._mark_used("bank_rate_epochs")
        best: BankRateEpoch | None = None
        for epoch in self._bank_rate_epochs:
            if epoch.from_date is None or epoch.from_date <= day:
                if best is None or (epoch.from_date or date.min) > (best.from_date or date.min):
                    best = epoch
        if best is None:
            raise NoEpochFound(
                f"no bank_rate_epochs entry covers {day.isoformat()}; "
                "fill earlier epochs from RBI (V1) before computing interest for that date"
            )
        return best.bank_rate_pct

    def bank_rate_epochs(self) -> list[BankRateEpoch]:
        """The Bank Rate epochs in ascending order, for splitting a delay period.

        Reading them records usage, so a period that actually spanned a rate
        change reports `bank_rate_epochs` among its unverified constants. The
        epochs are returned as stored; `from_date` is the first day each rate
        applies, and None marks the undated fallback.
        """
        self._mark_used("bank_rate_epochs")
        return list(self._bank_rate_epochs)

    def statutory_rate_on(self, day: date) -> Decimal:
        """s.16 statutory rate on `day`: interest_multiplier x Bank Rate."""
        return self.interest_multiplier() * self.bank_rate_on(day)

    def size_limits_on(self, day: date) -> SizeEpoch | None:
        """The size-epoch covering `day`, or None if nothing (not even the
        undated fallback) applies.

        Records usage only when an epoch is actually found, so an unmatched date
        does not report a constant it never used.
        """
        best: SizeEpoch | None = None
        for epoch in self._size_epochs:
            if epoch.from_date is None or epoch.from_date <= day:
                if best is None or (epoch.from_date or date.min) > (best.from_date or date.min):
                    best = epoch
        if best is not None:
            self._mark_used("size_epochs")
        return best

    def tax_preset(self, preset_id: str) -> TaxPreset | None:
        """Find a UI tax preset by id, recording usage only on a hit."""
        for preset in self._tax_presets:
            if preset.id == preset_id:
                self._mark_used("tax_presets")
                return preset
        return None

    def tax_presets(self) -> list[TaxPreset]:
        self._mark_used("tax_presets")
        return list(self._tax_presets)

    # -- public view for GET /api/v1/config ---------------------------------

    def public_config(self) -> dict[str, Any]:
        """A JSON-ready copy of every entry, for the assumptions drawer.

        Each key carries {value, source_ref, verified, note} exactly as stored, so
        the frontend can render verified flags without the loader's typed views.
        Dates are ISO strings; decimals stay strings to honour the contract's
        decimal-string convention.
        """
        out: dict[str, Any] = {}
        for key in sorted(self._entries):
            out[key] = {
                "value": self._public_value(key),
                "source_ref": self._entries[key]["source_ref"],
                "verified": self._entries[key]["verified"],
                "note": self._entries[key]["note"],
            }
        return out

    def _public_value(self, key: str) -> Any:
        if key == "bank_rate_epochs":
            return [
                {"from": e.from_date.isoformat() if e.from_date else None, "bank_rate_pct": str(e.bank_rate_pct)}
                for e in self._bank_rate_epochs
            ]
        if key == "size_epochs":
            return [
                {
                    "from": e.from_date.isoformat() if e.from_date else None,
                    **{
                        band: {
                            "investment_cr": str(getattr(e, band).investment_cr),
                            "turnover_cr": str(getattr(e, band).turnover_cr),
                        }
                        for band in ("micro", "small", "medium")
                    },
                }
                for e in self._size_epochs
            ]
        if key == "tax_presets":
            return [
                {"id": p.id, "label": p.label, "tax_rate_pct": str(p.tax_rate_pct)}
                for p in self._tax_presets
            ]
        value = self._entries[key]["value"]
        return value
