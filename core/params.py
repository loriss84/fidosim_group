"""Simulation parameters (SPEC section 4) with the v3.2 defaults.

Only machine names and numeric metadata live here; labels and one-line
explanations for the UI are in ``texts.py`` keyed by the same parameter key.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, asdict
from datetime import date
from typing import Any

import pandas as pd

DEFAULT_INTERCOMPANY = ["30001069", "30005389", "30001070"]  # SIAD Bulgaria, SIAD MI, SIAD SpA
DEFAULT_SPECIAL = ["S09", "EV9", "EV8", "EK9", "ES1", "ET1", "ET2", "ET8", "ET9", "EU9"]
DEFAULT_EXEMPT = ["A8", "EKM", "EPS", "EPU"]

ROUND_UP = "up"
ROUND_DOWN = "down"
DAYS_MEASURED = "measured"        # m1_days_basis: measured days (min, cap terms + X) - old v3
DAYS_CONTRACTUAL = "contractual"  # m1_days_basis: contractual terms (min, fallback days) - v3.1 default
# The v3.1 formula (decision of 21/11/2026, before v3.2): no customer-age bands, bonus / malus for every
# customer with measured days. ``Params(**V31)`` reproduces the v3.1 numbers exactly.
V31 = {"age_bands_enabled": False, "behaviour_min_invoices": 0}
# The old v3 formula (decisions of 20/11/2026, before v3.1): M1 on measured days, no bonus / malus
# (and, of course, no customer-age bands).
OLD_V3 = {"m1_days_basis": "measured", "behaviour_enabled": False, **V31}


@dataclass
class Params:
    """All formula parameters. Defaults = v3.2 rules decided for SIAD Romania (M1 on contractual
    terms + payment bonus / malus + customer-age bands); ``Params(**V31)`` = the v3.1 formula,
    ``Params(**OLD_V3)`` = the previous v3 formula."""

    # --- Country (Paese): currency, VAT prefix, local defaults, balance-sheet source (core.country) ---
    country: str = "RO"
    # --- Need (Bisogno) ---
    reference_date: str | None = None      # ISO date; None = latest AR124 invoice date
    window_months: int = 12                # payment-days look-back window
    fallback_days: int = 30                # days when neither invoices nor terms exist
    min_days: int = 15                     # floor on days used
    cap_extra_days: int = 15               # ceiling on days used = terms + this
    cap_days_enabled: bool = True          # apply the terms + X ceiling
    terms_positive_only: bool = True       # contractual terms from invoices > 0 only (False = legacy: all rows)
    m1_days_basis: str = DAYS_CONTRACTUAL  # days in M1: "contractual" terms (v3.1) | "measured" (old v3)
    buffer: float = 0.10                   # M1 safety buffer
    multiplier: float = 2.0                # base limit = multiplier x M1
    # --- Risk (Rischio) ---
    coef_reliable: float = 1.0             # AFFIDABILE
    coef_caution: float = 0.7              # CAUTELA
    coef_max_caution: float = 0.0          # MASSIMA CAUTELA
    coef_not_in_cerved: float = 0.5        # not in Cerved or no score
    coef_exempt_not_in_cerved: float = 0.5 # exempt classes not in Cerved
    cerved_reject_vat_conflict: bool = True  # code match with a different VAT is not used (False = legacy)
    # --- Payment behaviour (Comportamento di pagamento): bonus / malus on the limit (v3.1; off = old v3) ---
    behaviour_enabled: bool = True         # apply the bonus / malus (x (1 + pct) after the risk factor)
    behaviour_bonus_max: float = 0.05      # delay <= 0 (on time or early): +5%
    behaviour_malus_max: float = 0.10      # delay >= full_malus_days: -10%
    behaviour_tolerance_days: int = 5      # 0 < delay <= tolerance: 0%
    behaviour_full_malus_days: int = 30    # malus linear from 0 at tolerance to -malus_max here
    # --- Customer age (Anzianita cliente), v3.2: age = months from the first AR124 invoice to the reference date ---
    age_bands_enabled: bool = True         # NEW / YOUNG customers: monthly revenue = turnover / months active
    new_customer_months: int = 3           # age < this: NEW (annualised revenue, no bonus / malus)
    consolidated_months: int = 12          # age >= this: CONSOLIDATED (turnover / 12, as v3.1)
    behaviour_min_invoices: int = 3        # invoices > 0 already due (payment-days window) needed for the bonus / malus
    # --- Ceilings and rounding (Tetti e arrotondamenti) ---
    cerved_cap_enabled: bool = True        # min(limit, Cerved suggested limit)
    ceiling_is_hard: bool = True           # rounding/minimum never exceed the Cerved limit
    eur_rate: float = 4.975                # local currency per 1 EUR (RON for Romania)
    rounding_step: int = 1000
    rounding_mode: str = ROUND_UP          # "up" | "down"
    min_limit: int = 5000                  # minimum for limits > 0 (whole units of local currency)
    # --- Controls (Controlli) ---
    plausibility_threshold: float = 0.10   # turnover SIAD / total turnover
    approval_threshold: float = 0.20       # |change| vs current limit
    approval_min_change: int = 5000    # materiality: approval only if |change| is also above this
    tier1_eur: float = 50000.0
    tier2_eur: float = 200000.0
    # --- Populations (lists) ---
    intercompany_codes: list[str] = field(default_factory=lambda: list(DEFAULT_INTERCOMPANY))
    special_classes: list[str] = field(default_factory=lambda: list(DEFAULT_SPECIAL))
    exempt_classes: list[str] = field(default_factory=lambda: list(DEFAULT_EXEMPT))

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        """Normalise the lists: classes stripped and upper case; codes like the loaders do
        (spaces stripped, trailing '.0' removed, numeric codes by integer value). Integer
        parameters given as whole floats (5000.0) become int."""
        for key, meta in PARAM_META.items():
            v = getattr(self, key, None)
            if meta["kind"] == "int" and isinstance(v, float) and not isinstance(v, bool) \
                    and v == v and float(v).is_integer():
                setattr(self, key, int(v))
        if isinstance(self.country, str):
            self.country = self.country.strip().upper()
        for key in ("special_classes", "exempt_classes"):
            v = getattr(self, key)
            if isinstance(v, (list, tuple)):
                setattr(self, key, _unique([str(x).strip().upper() for x in v if str(x).strip()]))
        v = self.intercompany_codes
        if isinstance(v, (list, tuple)):
            self.intercompany_codes = _unique([c for c in (normalize_code(x) for x in v) if c])

    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Return a list of problems (empty = valid). Messages are keys + values, not UI text."""
        errs: list[str] = []
        for key, meta in PARAM_META.items():
            if meta["kind"] not in ("int", "float"):
                continue
            v = getattr(self, key)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or pd.isna(v):
                errs.append(f"{key}: not a number ({v!r})")
                continue
            if v < meta["min"] or v > meta["max"]:
                errs.append(f"{key}: {v} outside [{meta['min']}, {meta['max']}]")
            elif meta["kind"] == "int" and float(v) != int(v):
                errs.append(f"{key}: must be a whole number ({v!r})")
        if self.country not in PARAM_META["country"]["choices"]:
            errs.append(f"country: {self.country!r} not in {PARAM_META['country']['choices']}")
        if self.rounding_mode not in (ROUND_UP, ROUND_DOWN):
            errs.append(f"rounding_mode: {self.rounding_mode!r} not in ('up', 'down')")
        if self.m1_days_basis not in (DAYS_MEASURED, DAYS_CONTRACTUAL):
            errs.append(f"m1_days_basis: {self.m1_days_basis!r} not in ('measured', 'contractual')")
        if isinstance(self.behaviour_full_malus_days, (int, float)) \
                and isinstance(self.behaviour_tolerance_days, (int, float)) \
                and self.behaviour_full_malus_days <= self.behaviour_tolerance_days:
            errs.append("behaviour_full_malus_days: must be > behaviour_tolerance_days")
        if isinstance(self.new_customer_months, (int, float)) \
                and isinstance(self.consolidated_months, (int, float)) \
                and self.new_customer_months > self.consolidated_months:
            errs.append("new_customer_months: must be <= consolidated_months")
        if self.tier2_eur < self.tier1_eur:
            errs.append("tier2_eur: must be >= tier1_eur")
        if self.reference_date is not None:
            try:
                pd.Timestamp(self.reference_date)
            except Exception:
                errs.append(f"reference_date: invalid date {self.reference_date!r}")
        for key in ("intercompany_codes", "special_classes", "exempt_classes"):
            v = getattr(self, key)
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errs.append(f"{key}: must be a list of strings")
        return errs

    def check(self) -> "Params":
        """Raise ValueError if invalid, else return self."""
        errs = self.validate()
        if errs:
            raise ValueError("Invalid parameters: " + "; ".join(errs))
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kw: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, **kw)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Params":
        """Build from a dict; unknown keys are ignored, missing keys take defaults."""
        known = {f.name for f in fields(cls)}
        kw: dict[str, Any] = {}
        d = {OLD_NAMES.get(k, k): v for k, v in d.items() if OLD_NAMES.get(k, k) not in d or k not in OLD_NAMES}
        for k, v in d.items():
            if k not in known:
                continue
            meta = PARAM_META.get(k, {})
            kind = meta.get("kind")
            if kind == "int" and v is not None:
                v = int(round(float(v)))  # whole numbers (a JSON 5000.5 becomes 5000)
            elif kind == "float" and v is not None:
                v = float(v)
            elif kind == "bool":
                v = bool(v)
            elif kind == "list":
                v = [str(x).strip() for x in v]
            elif kind == "date" and v is not None:
                v = _iso(v)
            kw[k] = v
        return cls(**kw)

    @classmethod
    def from_json(cls, s: str) -> "Params":
        return cls.from_dict(json.loads(s))

    @classmethod
    def for_country(cls, code: str | None, **kw: Any) -> "Params":
        """Default formula with the local defaults of a country (currency amounts, intercompany)."""
        from .country import get
        d = get(code).param_defaults()
        d.update(kw)
        return cls.from_dict(d)

    def replace(self, **changes: Any) -> "Params":
        """Copy with some values changed (keys validated against the dataclass)."""
        d = self.to_dict()
        for k in changes:
            if k not in d:
                raise KeyError(f"unknown parameter {k!r}")
        d.update(changes)
        return Params.from_dict(d)

    def diff(self, other: "Params") -> dict[str, tuple[Any, Any]]:
        """Parameters that differ: key -> (self value, other value)."""
        a, b = self.to_dict(), other.to_dict()
        return {k: (a[k], b[k]) for k in a if a[k] != b[k]}


def normalize_code(x: Any) -> str | None:
    """Customer code as the loaders read it (see ``loaders.code_to_str``)."""
    from .loaders import code_to_str
    return code_to_str(x)


def _unique(xs: list[str]) -> list[str]:
    return list(dict.fromkeys(xs))


def _iso(v: Any) -> str:
    if isinstance(v, (date, pd.Timestamp)):
        return pd.Timestamp(v).date().isoformat()
    return pd.Timestamp(str(v)).date().isoformat()


def _m(group: str, kind: str, mn: float | None = None, mx: float | None = None,
       step: float | None = None, unit: str = "", primary: bool = True,
       sensitivity: bool = False) -> dict[str, Any]:
    return dict(group=group, kind=kind, min=mn, max=mx, step=step, unit=unit,
                primary=primary, sensitivity=sensitivity)


# UI metadata. group keys: need / risk / caps / controls / populations.
# unit keys: "months", "days", "pct" (value is a fraction, show x100), "x" (multiplier),
# "coef", "LOCAL" (local currency), "EUR", "LOCAL/EUR", "invoices", "" ; sensitivity=True -> offered in the sensitivity analysis.
# primary=True -> suggested for the Laboratory panel (19 of them: the 15 of v3.1 + the 4 customer-age ones);
# the others are still valid parameters (Data page, advanced, or fixed).
PARAM_META: dict[str, dict[str, Any]] = {
    "country": _m("populations", "choice", primary=False),
    "reference_date": _m("need", "date", primary=False),
    "window_months": _m("need", "int", 1, 36, 1, "months", primary=False, sensitivity=True),
    "fallback_days": _m("need", "int", 0, 365, 5, "days", primary=False, sensitivity=True),
    "min_days": _m("need", "int", 0, 180, 5, "days", sensitivity=True),
    "cap_extra_days": _m("need", "int", 0, 365, 5, "days", sensitivity=True),
    "cap_days_enabled": _m("need", "bool", primary=False),
    "terms_positive_only": _m("need", "bool", primary=False),
    "m1_days_basis": _m("need", "choice"),
    "buffer": _m("need", "float", 0.0, 1.0, 0.05, "pct", sensitivity=True),
    "multiplier": _m("need", "float", 0.0, 6.0, 0.1, "x", sensitivity=True),
    "coef_reliable": _m("risk", "float", 0.0, 1.0, 0.05, "coef", sensitivity=True),
    "coef_caution": _m("risk", "float", 0.0, 1.0, 0.05, "coef", sensitivity=True),
    "coef_max_caution": _m("risk", "float", 0.0, 1.0, 0.05, "coef", sensitivity=True),
    "coef_not_in_cerved": _m("risk", "float", 0.0, 1.0, 0.05, "coef", sensitivity=True),
    "coef_exempt_not_in_cerved": _m("risk", "float", 0.0, 1.0, 0.05, "coef", primary=False, sensitivity=True),
    "cerved_reject_vat_conflict": _m("risk", "bool", primary=False),
    # payment behaviour: only the switch is primary; the four values are shown in the Lab when it is on
    "behaviour_enabled": _m("behaviour", "bool"),
    "behaviour_bonus_max": _m("behaviour", "float", 0.0, 0.5, 0.01, "pct", primary=False, sensitivity=True),
    "behaviour_malus_max": _m("behaviour", "float", 0.0, 0.5, 0.01, "pct", primary=False, sensitivity=True),
    "behaviour_tolerance_days": _m("behaviour", "int", 0, 365, 1, "days", primary=False, sensitivity=True),
    "behaviour_full_malus_days": _m("behaviour", "int", 1, 730, 5, "days", primary=False, sensitivity=True),
    # customer age (v3.2): the four of them are primary (decision of the user, 21/11/2026)
    "age_bands_enabled": _m("age", "bool"),
    "new_customer_months": _m("age", "int", 0, 36, 1, "months", sensitivity=True),
    "consolidated_months": _m("age", "int", 1, 60, 1, "months", sensitivity=True),
    "behaviour_min_invoices": _m("age", "int", 0, 100, 1, "invoices", sensitivity=True),
    "cerved_cap_enabled": _m("caps", "bool"),
    "ceiling_is_hard": _m("caps", "bool", primary=False),
    "eur_rate": _m("caps", "float", 0.0001, 10000.0, 0.0005, "LOCAL/EUR", primary=False),
    "rounding_step": _m("caps", "int", 1, 10_000_000, 500, "LOCAL", primary=False),
    "rounding_mode": _m("caps", "choice"),
    "min_limit": _m("caps", "int", 0, 100_000_000, 1000, "LOCAL", sensitivity=True),
    "plausibility_threshold": _m("controls", "float", 0.0, 1.0, 0.01, "pct", sensitivity=True),
    "approval_threshold": _m("controls", "float", 0.0, 5.0, 0.05, "pct", sensitivity=True),
    "approval_min_change": _m("controls", "int", 0, 10_000_000_000, 1000, "LOCAL", primary=False),
    "tier1_eur": _m("controls", "float", 0.0, 1e8, 10000.0, "EUR", primary=False),
    "tier2_eur": _m("controls", "float", 0.0, 1e8, 10000.0, "EUR", primary=False),
    "intercompany_codes": _m("populations", "list", primary=False),
    "special_classes": _m("populations", "list", primary=False),
    "exempt_classes": _m("populations", "list", primary=False),
}
PARAM_META["rounding_mode"]["choices"] = [ROUND_UP, ROUND_DOWN]
PARAM_META["country"]["choices"] = ["RO", "SK", "AT", "CZ", "DE", "HU"]
# Parameter names of the single-country simulator (scenario files saved before the rename load as they are).
OLD_NAMES = {"eur_ron": "eur_rate", "approval_min_change_ron": "approval_min_change"}
PARAM_META["m1_days_basis"]["choices"] = [DAYS_MEASURED, DAYS_CONTRACTUAL]

PARAM_GROUPS = ["need", "risk", "behaviour", "age", "caps", "controls", "populations"]

# sanity: metadata covers every field
assert set(PARAM_META) == {f.name for f in fields(Params)}, "PARAM_META out of sync"
