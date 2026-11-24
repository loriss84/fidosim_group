"""Reason codes, "why it changes vs current" codes and the step-by-step calculation.

Only codes and numbers here; the sentences are in ``texts.py`` (REASON_TEXTS,
CHANGE_TEXTS, STEP_TEXTS), filled with the values returned by ``text_values``.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .loaders import local_currency

# Reason codes, in priority order (first true wins).
R_INTERCOMPANY = "R_INTERCOMPANY"
R_SPECIAL = "R_SPECIAL"
R_NO_TURNOVER = "R_NO_TURNOVER"
R_MAX_CAUTION = "R_MAX_CAUTION"          # score MASSIMA CAUTELA with coefficient 0
R_ZERO_COEF = "R_ZERO_COEF"              # any other coefficient 0
R_CERVED_ZERO = "R_CERVED_ZERO"          # Cerved suggested limit = 0
R_ROUNDED_ZERO = "R_ROUNDED_ZERO"        # rounding down brought the limit to 0
R_MINIMUM_OVER_CAP = "R_MINIMUM_OVER_CAP"  # Cerved cap binds but the minimum lifts it
R_CERVED_CAP = "R_CERVED_CAP"
R_MINIMUM = "R_MINIMUM"
R_COEF_CAUTION = "R_COEF_CAUTION"
R_COEF_NOT_IN_CERVED = "R_COEF_NOT_IN_CERVED"
R_COEF_REDUCED = "R_COEF_REDUCED"        # coefficient < 1 for another reason (e.g. user set)
R_FULL_NEED_NEUTRAL = "R_FULL_NEED_NEUTRAL"  # full need without a reliable score (coefficient set to 1)
R_FULL_NEED = "R_FULL_NEED"              # full need, score AFFIDABILE
R_BEHAVIOUR_BONUS = "R_BEHAVIOUR_BONUS"  # overlay: the payment bonus decided the limit (formula-driven limit)
R_BEHAVIOUR_MALUS = "R_BEHAVIOUR_MALUS"  # overlay: the payment malus decided the limit
R_NEW_CUSTOMER = "R_NEW_CUSTOMER"        # overlay (v3.2): formula on the annualised revenue of a new customer
R_YOUNG_CUSTOMER = "R_YOUNG_CUSTOMER"    # overlay (v3.2): formula on the annualised revenue of a young customer
_PRIORITY = [R_INTERCOMPANY, R_SPECIAL, R_NO_TURNOVER, R_MAX_CAUTION, R_ZERO_COEF, R_CERVED_ZERO,
             R_ROUNDED_ZERO, R_MINIMUM_OVER_CAP, R_CERVED_CAP, R_MINIMUM, R_COEF_CAUTION,
             R_COEF_NOT_IN_CERVED, R_COEF_REDUCED, R_FULL_NEED_NEUTRAL, R_FULL_NEED]
REASON_CODES = _PRIORITY + [R_BEHAVIOUR_BONUS, R_BEHAVIOUR_MALUS, R_NEW_CUSTOMER, R_YOUNG_CUSTOMER]
# reasons where the limit is the formula itself (risk factor / full need): only there the payment
# bonus or malus can be the decisive reason (zero rules, the Cerved ceiling and the minimum win)
FORMULA_REASONS = {R_COEF_CAUTION, R_COEF_NOT_IN_CERVED, R_COEF_REDUCED, R_FULL_NEED_NEUTRAL, R_FULL_NEED}

# Change codes ("why it changes vs current"). Every sentence is true for the customer it is used for:
# the Cerved-capped cases are split by what pushed the limit to the Cerved value (the formula itself,
# the minimum, or rounding up), and the minimum has its own codes.
C_EQUAL = "C_EQUAL"
C_EXCLUDED = "C_EXCLUDED"
C_HIGHER_NO_CURRENT = "C_HIGHER_NO_CURRENT"        # today 0 in CreditBoard, formula decides
C_HIGHER_MINIMUM = "C_HIGHER_MINIMUM"              # the minimum lifts it above today's limit
C_HIGHER_NEED = "C_HIGHER_NEED"                    # the formula gives more than today
C_HIGHER_ROUNDED = "C_HIGHER_ROUNDED"              # formula below today, rounding up takes it above
C_HIGHER_CERVED_CAP = "C_HIGHER_CERVED_CAP"        # higher, but held at the Cerved limit (formula above it)
C_HIGHER_MINIMUM_CAPPED = "C_HIGHER_MINIMUM_CAPPED"  # minimum would go above Cerved: Cerved limit
C_HIGHER_ROUNDED_CAPPED = "C_HIGHER_ROUNDED_CAPPED"  # rounding up would go above Cerved: Cerved limit
C_LOWER_SPECIAL = "C_LOWER_SPECIAL"
C_LOWER_NO_TURNOVER = "C_LOWER_NO_TURNOVER"
C_LOWER_MAX_CAUTION = "C_LOWER_MAX_CAUTION"
C_LOWER_ZERO_COEF = "C_LOWER_ZERO_COEF"
C_LOWER_CERVED_ZERO = "C_LOWER_CERVED_ZERO"
C_LOWER_ROUNDED_ZERO = "C_LOWER_ROUNDED_ZERO"
C_LOWER_CERVED_CAP = "C_LOWER_CERVED_CAP"          # the formula is above the Cerved limit
C_LOWER_MINIMUM_CAPPED = "C_LOWER_MINIMUM_CAPPED"
C_LOWER_ROUNDED_CAPPED = "C_LOWER_ROUNDED_CAPPED"
C_LOWER_MINIMUM = "C_LOWER_MINIMUM"
C_LOWER_CAUTION = "C_LOWER_CAUTION"
C_LOWER_NOT_IN_CERVED = "C_LOWER_NOT_IN_CERVED"
C_LOWER_COEF = "C_LOWER_COEF"
C_LOWER_NEED = "C_LOWER_NEED"
C_HIGHER_BONUS = "C_HIGHER_BONUS"    # without the bonus it would not be higher than today: the bonus decides
C_LOWER_MALUS = "C_LOWER_MALUS"      # without the malus it would not be lower than today: the malus decides
C_HIGHER_AGE = "C_HIGHER_AGE"        # v3.2: formula on the revenue of a new / young customer (turnover / months active)
C_LOWER_AGE = "C_LOWER_AGE"          # v3.2: lower even with the turnover divided by the months active
_LOWER_BY_REASON = {
    R_SPECIAL: C_LOWER_SPECIAL, R_NO_TURNOVER: C_LOWER_NO_TURNOVER, R_MAX_CAUTION: C_LOWER_MAX_CAUTION,
    R_ZERO_COEF: C_LOWER_ZERO_COEF, R_CERVED_ZERO: C_LOWER_CERVED_ZERO, R_ROUNDED_ZERO: C_LOWER_ROUNDED_ZERO,
    R_CERVED_CAP: C_LOWER_CERVED_CAP, R_COEF_CAUTION: C_LOWER_CAUTION,
    R_COEF_NOT_IN_CERVED: C_LOWER_NOT_IN_CERVED, R_COEF_REDUCED: C_LOWER_COEF,
    R_MINIMUM: C_LOWER_MINIMUM, R_MINIMUM_OVER_CAP: C_LOWER_MINIMUM, R_FULL_NEED: C_LOWER_NEED,
    R_FULL_NEED_NEUTRAL: C_LOWER_NEED,
}
CHANGE_CODES = [C_EQUAL, C_EXCLUDED, C_HIGHER_NO_CURRENT, C_HIGHER_MINIMUM, C_HIGHER_NEED, C_HIGHER_ROUNDED,
                C_HIGHER_CERVED_CAP, C_HIGHER_MINIMUM_CAPPED, C_HIGHER_ROUNDED_CAPPED,
                C_LOWER_MINIMUM_CAPPED, C_LOWER_ROUNDED_CAPPED, C_HIGHER_BONUS, C_LOWER_MALUS,
                C_HIGHER_AGE, C_LOWER_AGE] \
    + sorted(set(_LOWER_BY_REASON.values()))


def reason_codes(r: pd.DataFrame, behaviour: bool = True) -> np.ndarray:
    """Vectorised reason code per row of the engine result (priority order of SPEC 4).

    With ``behaviour`` (and the columns ``behaviour_pct`` / ``behaviour_effect`` present) the
    payment-behaviour overlay of ``behaviour_reasons`` is applied.

    The Cerved tests use the ceiling in whole RON (``ceiling_unit``): a Cerved value of 0,40 RON
    gives a limit of 0 and the reason "Cerved suggests 0"; a final limit equal to the whole-RON
    ceiling because of the cap is always "limited by Cerved".
    """
    coef = r["coefficient"].to_numpy()
    has_ceiling = r["ceiling"].notna().to_numpy()
    unit = np.nan_to_num(r["ceiling_unit"].to_numpy(dtype=float), nan=np.inf)
    prop = r["proposed_limit"].to_numpy()
    hard = r["hard_cap_applied"].to_numpy(bool)
    b = r["score_bucket"]
    conds = [
        r["is_intercompany"],
        r["is_special"],
        r["turnover_12m"] <= 0,
        (coef == 0) & b.eq("MASSIMA CAUTELA"),
        coef == 0,
        has_ceiling & (unit <= 0) & (prop <= 0),
        (prop <= 0) & ~hard,
        r["ceiling_binds"] & r["min_applied"] & (prop > unit),
        r["ceiling_binds"] | hard,
        r["min_applied"],
        (coef < 1) & b.eq("CAUTELA"),
        (coef < 1) & b.eq("NONE"),
        coef < 1,
        ~b.eq("AFFIDABILE"),
    ]
    base = np.select([np.asarray(c, bool) for c in conds], _PRIORITY[:-1], R_FULL_NEED).astype(object)
    return behaviour_reasons(r, base) if behaviour else base


def behaviour_reasons(r: pd.DataFrame, base: np.ndarray) -> np.ndarray:
    """Overlay: where the limit is the formula itself (``FORMULA_REASONS``) and the payment bonus /
    malus changed the final limit (``behaviour_effect`` at least 0,5 RON), the reason is
    R_BEHAVIOUR_BONUS / R_BEHAVIOUR_MALUS. Zero rules, Cerved ceiling and minimum keep their reason."""
    if "behaviour_effect" not in r or "behaviour_pct" not in r:
        return base
    eff = np.abs(r["behaviour_effect"].to_numpy(dtype=float)) >= 0.5
    pct = r["behaviour_pct"].to_numpy(dtype=float)
    dec = eff & pd.Series(base).isin(FORMULA_REASONS).to_numpy()
    return np.where(dec & (pct > 0), R_BEHAVIOUR_BONUS,
                    np.where(dec & (pct < 0), R_BEHAVIOUR_MALUS, base)).astype(object)


AGE_REASONS = {R_NEW_CUSTOMER, R_YOUNG_CUSTOMER}


def age_reasons(r: pd.DataFrame, reason: np.ndarray, params: Any) -> np.ndarray:
    """Overlay (v3.2): where the limit is still the formula itself (``FORMULA_REASONS``, i.e. not zero
    rules, Cerved ceiling, minimum or a decisive bonus / malus) and the customer's turnover was divided
    by fewer than 12 months active (NEW / YOUNG band, age bands on), the reason is R_NEW_CUSTOMER /
    R_YOUNG_CUSTOMER: the annualised revenue is what drives the limit."""
    if not getattr(params, "age_bands_enabled", False) or "age_band" not in r:
        return reason
    band = r["age_band"].to_numpy(dtype=object)
    # fewer than 12 months active as shown (one decimal): 11,97 months reads "12" and changes ~0,3%
    short = np.round(r["months_active"].to_numpy(dtype=float), 1) < 12.0
    formula = pd.Series(reason).isin(FORMULA_REASONS).to_numpy()
    return np.where(formula & short & (band == "NEW"), R_NEW_CUSTOMER,
                    np.where(formula & short & (band == "YOUNG"), R_YOUNG_CUSTOMER, reason)).astype(object)


def change_codes(r: pd.DataFrame) -> np.ndarray:
    """Vectorised "why it changes vs the current limit" code (sentences always true for the row)."""
    reason = pd.Series(r["reason_code"].to_numpy(), index=r.index)
    # the payment bonus / malus overlay: the other codes follow the reason without it
    base_reason = pd.Series(r["reason_base_code"].to_numpy(), index=r.index) if "reason_base_code" in r \
        else reason
    cap = reason.eq(R_CERVED_CAP).to_numpy()
    binds = r["ceiling_binds"].to_numpy(bool)                     # the formula itself is above Cerved
    rounded, after_min = r["limit_rounded"].to_numpy(), r["limit_after_minimum"].to_numpy()
    min_pushed = (rounded > 0) & (after_min > rounded)            # the minimum lifted it
    lower = base_reason.map(_LOWER_BY_REASON).fillna(C_LOWER_NEED).to_numpy()
    lower = np.select([cap & binds, cap & min_pushed, cap], [C_LOWER_CERVED_CAP, C_LOWER_MINIMUM_CAPPED,
                                                            C_LOWER_ROUNDED_CAPPED], lower)
    higher = np.select(
        [cap & binds, cap & min_pushed, cap,
         reason.isin([R_MINIMUM, R_MINIMUM_OVER_CAP]).to_numpy(), r["current_limit"].to_numpy() <= 0,
         _after_behaviour(r) < r["current_limit"].to_numpy()],
        [C_HIGHER_CERVED_CAP, C_HIGHER_MINIMUM_CAPPED, C_HIGHER_ROUNDED_CAPPED,
         C_HIGHER_MINIMUM, C_HIGHER_NO_CURRENT, C_HIGHER_ROUNDED], C_HIGHER_NEED)
    if "proposed_limit_no_behaviour" in r:
        # decisive: without the bonus the limit would not be higher than today (malus: not lower)
        gap0 = r["proposed_limit_no_behaviour"].to_numpy() - r["current_limit"].to_numpy()
        cur_pos = r["current_limit"].to_numpy() > 0
        higher = np.where(reason.eq(R_BEHAVIOUR_BONUS).to_numpy() & (gap0 < 0.5) & cur_pos, C_HIGHER_BONUS, higher)
        lower = np.where(reason.eq(R_BEHAVIOUR_MALUS).to_numpy() & (gap0 > -0.5), C_LOWER_MALUS, lower)
    # new / young customer: the formula on the annualised revenue (the rounding-up case keeps its code)
    is_age = reason.isin(AGE_REASONS).to_numpy()
    higher = np.where(is_age & np.isin(higher, [C_HIGHER_NEED, C_HIGHER_NO_CURRENT]), C_HIGHER_AGE, higher)
    lower = np.where(is_age, C_LOWER_AGE, lower)
    d = r["direction"].to_numpy()
    out = np.where(d == "HIGHER", higher, np.where(d == "LOWER", lower, C_EQUAL))
    return np.where(r["is_intercompany"].to_numpy(), C_EXCLUDED, out).astype(object)


# ---------------------------------------------------------------------------
# Values for sentences and step by step
# ---------------------------------------------------------------------------
def _f(x: Any) -> Any:
    """Plain Python value (NaN -> None) for sentence formatting / JSON."""
    if x is None:
        return None
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else float(x)
    return x


def _after_behaviour(r: Any) -> Any:
    """The formula up to the payment behaviour (= limit after the risk factor when it is off)."""
    col = "limit_after_behaviour" if "limit_after_behaviour" in r else "limit_after_coef"
    return r[col].to_numpy() if isinstance(r, pd.DataFrame) else r[col]


def _formula(row: pd.Series) -> float | None:
    """The formula result quoted in "the formula gives X": the limit before rounding, or the rounded
    value when rounding down made it smaller (so "below the minimum" / "lower" stay true)."""
    pre, rnd = _f(row["limit_before_rounding"]), _f(row["limit_rounded"])
    if pre is None:
        return None
    return min(pre, rnd) if rnd is not None and rnd > 0 else pre


def text_values(row: pd.Series, params: Any) -> dict[str, Any]:
    """Placeholders available to REASON_TEXTS / CHANGE_TEXTS for one customer."""
    lim_ron = _f(row["cerved_limit_ron"])
    return {
        "current": _f(row["current_limit"]), "proposed": _f(row["proposed_limit"]),
        "need": _f(row["m1"]), "base": _f(row["base_limit"]), "after_coef": _f(_after_behaviour(row)),
        "risk_limit": _f(row["limit_after_coef"]),
        "cerved_limit": _f(row["ceiling_unit"]) if pd.notna(row["ceiling"]) else
        (None if lim_ron is None else float(np.floor(round(lim_ron, 6)))),
        "bucket": row["score_bucket"], "before_round": _f(row["limit_before_rounding"]),
        "formula": _formula(row),
        "score": row["score"] if isinstance(row["score"], str) else None,
        "coefficient": _f(row["coefficient"]), "min_limit": _f(params.min_limit),
        "risk_class": row["risk_class"], "diff": _f(row["diff"]),
        "days_used": _f(row["days_used"]), "days_measured": _f(row["days_measured"]),
        "days_max": _f(row["days_max"]), "mult": _f(getattr(params, "multiplier", None)),
        "buffer": _f(getattr(params, "buffer", None)),
        # payment behaviour: delay = measured days - terms; pct signed, pct_abs for "malus 6%"
        "delay": _f(row.get("delay_days")), "days_terms": _f(row.get("days_terms")),
        "behaviour_pct": _f(row.get("behaviour_pct")),
        "behaviour_pct_abs": None if _f(row.get("behaviour_pct")) is None else abs(float(row["behaviour_pct"])),
        "no_behaviour": _f(row.get("proposed_limit_no_behaviour")),
        # customer age (v3.2): age in months, months active, monthly revenue used, turnover
        "age": _f(row.get("age_months")), "months": _f(row.get("months_active")),
        "monthly": _f(row.get("monthly_revenue_used")), "turnover": _f(row["turnover_12m"]),
        "monthly12": max(float(row["turnover_12m"]), 0.0) / 12,
        "age_source_code": row.get("age_source") if isinstance(row.get("age_source"), str) else None,
        "inv_due": _f(row.get("behaviour_invoices_n")),
        "min_invoices": _f(getattr(params, "behaviour_min_invoices", None)),
    }


def steps(row: pd.Series, params: Any) -> list[dict[str, Any]]:
    """Step-by-step calculation for one customer (a row of ``simulate``).

    Returns a list of ``{"step": key, "values": {...}, "amount": float|None, "unit": "RON"|"days"|""}``.
    ``step`` is a key of texts.STEP_TEXTS; ``values`` fill its placeholders.
    """
    p = params
    out: list[dict[str, Any]] = []

    def add(key: str, amount: Any = None, unit: str = "RON", **values: Any) -> None:
        out.append({"step": key, "values": {k: _f(v) for k, v in values.items()},
                    "amount": _f(amount), "unit": unit})

    if bool(row["is_intercompany"]):
        add("S_INTERCOMPANY", 0.0, code=row["code"])
        return out

    add("S_TURNOVER", row["turnover_12m"])
    if getattr(p, "age_bands_enabled", False) and "age_band" in row:
        band = row["age_band"]
        src = row.get("age_source")
        key = {"NEW": "S_AGE_NEW", "YOUNG": "S_AGE_YOUNG", "CONSOLIDATED": "S_AGE_CONSOLIDATED"}.get(
            band, "S_AGE_NO_HISTORY")
        if band == "CONSOLIDATED" and bool(row.get("age_censored", False)):
            key = "S_AGE_CENSORED"
        add(key, row["monthly_revenue_used"], first=_date(row.get("age_start_date")),
            src={"md105": "MD105", "ar124_earlier": "AR124 < MD105", "ar124": "AR124"}.get(src, "-")
            if isinstance(src, str) else "-",
            age=row["age_months"], months=row["months_active"], turnover=row["turnover_12m"],
            new=p.new_customer_months, consolidated=p.consolidated_months,
            ar_start=_date(row.get("ar_start_date")))
    src = row["days_source"]
    if src == "contractual":
        add("S_DAYS_CONTRACTUAL", row["days_terms"], "days")
    elif src == "measured":
        add("S_DAYS_MEASURED", row["days_measured"], "days", n=row["n_invoices"],
            window=p.window_months)
    elif src == "terms":
        add("S_DAYS_TERMS", row["days_terms"], "days")
    else:
        add("S_DAYS_FALLBACK", p.fallback_days, "days", fallback=p.fallback_days)
    add("S_TERMS", row["days_terms"], "days")
    if bool(row["days_min_applied"]):
        add("S_DAYS_MIN", p.min_days, "days", raw=row["days_raw"], min_days=p.min_days)
    if bool(row["days_capped"]):
        add("S_DAYS_CAPPED", row["days_max"], "days", raw=max(row["days_raw"], p.min_days),
            terms=row["days_max"] - p.cap_extra_days, extra=p.cap_extra_days)
    add("S_DAYS_USED", row["days_used"], "days")
    add("S_M1", row["m1"], turnover=row["turnover_12m"], days=row["days_used"], buffer=p.buffer,
        months=row.get("months_active", 12.0))
    add("S_BASE", row["base_limit"], multiplier=p.multiplier, m1=row["m1"])
    add("S_COEF", row["limit_after_coef"], score=row["score"] if row["score_bucket"] != "NONE" else None,
        bucket=row["score_bucket"], coefficient=row["coefficient"], base=row["base_limit"],
        exempt=row["is_exempt"])
    if getattr(p, "behaviour_enabled", False):
        add(behaviour_step(row), row["limit_after_behaviour"], before=row["limit_after_coef"],
            delay=row["delay_days"], measured=row["days_measured"], terms=row["days_terms"],
            pct=row["behaviour_pct"], pct_abs=abs(float(row["behaviour_pct"])),
            tolerance=p.behaviour_tolerance_days, full=p.behaviour_full_malus_days,
            n=row.get("behaviour_invoices_n"), min_invoices=getattr(p, "behaviour_min_invoices", 0),
            new=getattr(p, "new_customer_months", None))
    if not p.cerved_cap_enabled:
        add("S_CEILING_DISABLED", row["limit_after_ceiling"])
    elif pd.isna(row["ceiling"]):
        invalid = bool(row["in_cerved"]) and pd.notna(row["cerved_limit_orig"]) \
            and not bool(row["cerved_limit_usable"])
        add("S_CEILING_INVALID" if invalid else "S_NO_CEILING", row["limit_after_ceiling"],
            in_cerved=row["in_cerved"], orig=row["cerved_limit_orig"],
            currency=row["cerved_currency"] if isinstance(row["cerved_currency"], str) else local_currency())
    else:
        ceil_shown = row["ceiling_unit"] if p.ceiling_is_hard else row["ceiling"]  # whole RON (hard cap)
        add("S_CEILING_BINDS" if bool(row["ceiling_binds"]) else "S_CEILING_NOT_BINDING",
            row["limit_after_ceiling"], ceiling=ceil_shown, orig=row["cerved_limit_orig"],
            currency=row["cerved_currency"] if isinstance(row["cerved_currency"], str) else local_currency(),
            eur_rate=p.eur_rate, before=_after_behaviour(row))
    if bool(row["zero_special"]):
        add("S_ZERO_SPECIAL", 0.0, risk_class=row["risk_class"])
    elif bool(row["zero_no_turnover"]):
        add("S_ZERO_NO_TURNOVER", 0.0)
    add("S_ROUND_UP" if p.rounding_mode == "up" else "S_ROUND_DOWN", row["limit_rounded"],
        step=p.rounding_step, before=row["limit_before_rounding"])
    if bool(row["min_applied"]) or (bool(row["hard_cap_applied"]) and
                                    0 < row["limit_rounded"] < p.min_limit):
        add("S_MINIMUM", row["limit_after_minimum"], min_limit=p.min_limit, before=row["limit_rounded"])
    if bool(row["hard_cap_applied"]):
        add("S_HARD_CAP", row["proposed_limit"], ceiling=row["ceiling_unit"], step=p.rounding_step,
            before=row["limit_after_minimum"], final=row["proposed_limit"])
    add("S_PROPOSED", row["proposed_limit"])
    add("S_CURRENT", row["current_limit"], diff=row["diff"], diff_pct=row["diff_pct"])
    return out


def behaviour_step(row: pd.Series) -> str:
    """STEP_TEXTS key of the payment-behaviour step for this customer."""
    return {"BONUS": "S_BEHAVIOUR_BONUS", "TOLERANCE": "S_BEHAVIOUR_TOLERANCE",
            "MALUS": "S_BEHAVIOUR_MALUS", "NEW_CUSTOMER": "S_BEHAVIOUR_NEW",
            "FEW_INVOICES": "S_BEHAVIOUR_FEW"}.get(row["behaviour_band"], "S_BEHAVIOUR_NONE")


def _date(x: Any) -> str | None:
    """dd/mm/yyyy (None for a missing date)."""
    return None if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y")


def explain_customer(result: pd.DataFrame, code: str, params: Any) -> dict[str, Any]:
    """Everything the Customer page needs for one code: reason, change, steps, controls."""
    from .loaders import code_to_str
    m = result[result["code"] == code_to_str(code)]
    if m.empty:
        raise KeyError(f"customer {code!r} not in the result")
    row = m.iloc[0]
    return {
        "code": row["code"], "name": row["name"],
        "reason_code": row["reason_code"], "change_code": row["change_code"],
        "values": text_values(row, params), "steps": steps(row, params),
        "controls": {k: _f(row[k]) for k in (
            "exposure", "overdue", "ordered", "in_scope", "is_exempt", "is_special",
            "over_new", "over_current", "excess_new", "excess_current",
            "plausibility_ratio", "plausibility_flag", "approval_needed", "tier",
            "proposed_limit_eur", "days_capped", "hard_cap_applied", "min_applied",
            "delay_days", "behaviour_pct", "behaviour_band", "limit_after_behaviour",
            "proposed_limit_no_behaviour", "behaviour_effect",
            "age_months", "age_band", "months_active", "monthly_revenue_used", "behaviour_invoices_n",
            "revenue_check_flag", "age_censored")},
        "first_invoice_date": _date(row.get("first_invoice_date")),
        "opened_date": _date(row.get("opened_date")), "age_start_date": _date(row.get("age_start_date")),
        "age_source": row.get("age_source") if isinstance(row.get("age_source"), str) else None,
        "cerved": {k: _f(row[k]) for k in (
            "in_cerved", "match_method", "cerved_name", "score", "cerved_limit_orig",
            "cerved_currency", "cerved_limit_ron", "cerved_limit_usable", "cerved_turnover",
            "reliability_class", "vat_differs", "vat_conflict")},
    }


def add_texts(result: pd.DataFrame, params: Any, lang: str = "it") -> pd.DataFrame:
    """Copy of ``result`` with readable ``reason`` and ``why_change`` columns in ``lang``."""
    from . import texts as T
    out = result.copy()
    reasons, changes = [], []
    for _, row in result.iterrows():
        v = text_values(row, params)
        reasons.append(T.t(T.REASON_TEXTS, row["reason_code"], lang, **v))
        changes.append(T.t(T.CHANGE_TEXTS, row["change_code"], lang, **v))
    out["reason"] = reasons
    out["why_change"] = changes
    return out


def steps_text(steps_list: list[dict[str, Any]], lang: str = "it") -> list[dict[str, Any]]:
    """Render ``steps`` into rows {step, label, calc, amount, unit} for a table."""
    from . import texts as T
    rows = []
    for s in steps_list:
        e = T.STEP_TEXTS.get(s["step"], {}).get(lang) or {"label": s["step"], "calc": ""}
        rows.append({"step": s["step"], "label": T.render(e["label"], lang, **s["values"]),
                     "calc": T.render(e["calc"], lang, **s["values"]),
                     "amount": s["amount"], "unit": s["unit"]})
    return rows
