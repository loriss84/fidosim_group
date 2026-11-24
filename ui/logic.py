"""Presentation logic without Streamlit: number formatting, table columns, the fixed
10-step table of the Customer page, parameter-change lists, rules text, quality table.

Everything here is a pure function of (core result, params, lang) so it can be tested
without running the app. All sentences come from ``core.texts``.
"""
from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from core import texts as TX
from core.loaders import LoadedData
from core import country as CO
from core.params import Params, PARAM_META

# Parameters that are data choices (Data page), not formula choices.
DATA_KEYS = ("country", "reference_date", "window_months")
BUCKET_ORDER = ["AFFIDABILE", "CAUTELA", "MASSIMA CAUTELA", "NONE"]
CHANGE_BUCKETS = ["TO_ZERO", "DOWN_50", "DOWN_20_50", "WITHIN_20", "UP_20_50", "UP_50", "FROM_ZERO"]
ZERO_REASONS = {"R_MAX_CAUTION", "R_CERVED_ZERO", "R_SPECIAL", "R_NO_TURNOVER", "R_ZERO_COEF",
                "R_ROUNDED_ZERO"}


# ---------------------------------------------------------------------------
# Formatting (UX.md 1.4)
# ---------------------------------------------------------------------------
def _bad(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or x is pd.NA


def num(x: Any, lang: str, decimals: int = 0) -> str:
    """1234.5 -> '1.235' (it) / '1,235' (en)."""
    if _bad(x):
        return "-"
    return TX.fmt_amount(float(x), lang, decimals)


def amt(x: Any, lang: str) -> str:
    """Amount with the local currency: '1.234.567 RON'."""
    return "-" if _bad(x) else f"{num(x, lang)} {CO.currency()}"


def mln(x: Any, lang: str) -> str:
    """'39,69 mln RON' / '39.69 M RON'."""
    if _bad(x):
        return "-"
    return f"{TX.fmt_amount(float(x) / 1e6, lang, 2)} {TX.T('mln', lang)}"


def big(x: Any, lang: str) -> str:
    """Tile value: millions from 1,000,000 up, full amount below."""
    return mln(x, lang) if not _bad(x) and abs(float(x)) >= 1e6 else amt(x, lang)


def whole_ron(x: Any) -> Any:
    """Cerved suggested limit in whole RON, as the engine uses it (4.582,72 -> 4.582)."""
    return x if _bad(x) else float(np.floor(round(float(x), 6)))


def signed(x: float, lang: str, decimals: int = 0) -> str:
    """Always a sign, ASCII minus: '+12', '-1.234'."""
    s = TX.fmt_amount(abs(float(x)), lang, decimals)
    return ("-" if x < 0 else "+") + s


def signed_big(x: float, lang: str, in_mln: bool) -> str:
    if in_mln:
        return ("-" if x < 0 else "+") + mln(abs(x), lang)
    return signed(x, lang) + " " + CO.currency()


def pct(x: Any, lang: str, decimals: int = 0) -> str:
    """Fraction -> '10%' / '12,5%'."""
    if _bad(x):
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "∞"
    return TX.fmt_amount(float(x) * 100, lang, decimals) + "%"


def signed_pct(x: Any, lang: str) -> str:
    if _bad(x) or (isinstance(x, float) and math.isinf(x)):
        return "-"
    return ("-" if x < 0 else "+") + pct(abs(float(x)), lang, 1)


def coef(x: Any, lang: str) -> str:
    return "-" if _bad(x) else TX.fmt_amount(float(x), lang, 2)


def days(x: Any, lang: str) -> str:
    return "-" if _bad(x) else f"{num(x, lang)} {TX.T('days_unit', lang)}"


def date_str(d: Any) -> str:
    """dd/mm/yyyy in both languages."""
    if _bad(d) or d is pd.NaT:
        return "-"
    try:
        return pd.Timestamp(d).strftime("%d/%m/%Y")
    except Exception:
        return "-"


AGE_ORDER = ["NEW", "YOUNG", "CONSOLIDATED", "NO_HISTORY"]


def age_label(band: Any, lang: str) -> str:
    return TX.T(f"age_{band if isinstance(band, str) else 'NO_HISTORY'}", lang)


def annualised(row: Any, p: Params) -> bool:
    """True when the turnover is divided by fewer than 12 months active (as shown, one decimal)."""
    return bool(p.age_bands_enabled) and round(float(row.get("months_active", 12.0)), 1) < 12.0


def score_label(bucket: Any, lang: str) -> str:
    return TX.T(f"score_{bucket if isinstance(bucket, str) else 'NONE'}", lang)


def param_value(key: str, value: Any, lang: str) -> str:
    """A parameter value as shown to people (unit per PARAM_META)."""
    meta = PARAM_META[key]
    kind, unit = meta["kind"], meta["unit"]
    if kind == "bool":
        return TX.T("on" if value else "off", lang)
    if kind == "choice" and key == "country":
        return CO.get(value).name(lang)
    if kind == "choice" and key == "m1_days_basis":
        return TX.T("p_m1_measured" if value == "measured" else "p_m1_contractual", lang)
    if kind == "choice":
        return TX.T("p_round_up" if value == "up" else "p_round_down", lang)
    if kind == "list":
        return ", ".join(value) if value else TX.T("none_word", lang)
    if kind == "date":
        return date_str(value) if value else TX.T("dash", lang)
    if unit == "pct":
        return pct(value, lang)
    if unit in ("coef", "x"):
        return coef(value, lang)
    if unit == "days":
        return days(value, lang)
    if unit == "LOCAL/EUR":
        return TX.fmt_amount(float(value), lang, 3)
    if unit in ("LOCAL", "EUR"):
        return num(value, lang)
    return num(value, lang)


def param_label(key: str, lang: str) -> str:
    return TX.T(TX.PARAM_LABEL_KEYS[key], lang)


# ---------------------------------------------------------------------------
# Scenario vs v3
# ---------------------------------------------------------------------------
def base_params(p: Params) -> Params:
    """The v3 default formula with the same data settings as ``p``."""
    return Params.for_country(p.country, **{k: getattr(p, k) for k in DATA_KEYS})


def formula_changes(p: Params, lang: str, sep: str = " · ") -> tuple[int, str]:
    """(number of formula parameters changed vs v3, 'Multiplier 2,00 → 2,50 · ...')."""
    d = base_params(p).diff(p)
    items = [f"{param_label(k, lang)} {param_value(k, a, lang)} → {param_value(k, b, lang)}"
             for k, (a, b) in d.items() if k not in DATA_KEYS]
    return len(items), sep.join(items)


def short_changes(params: Params, lang: str) -> str:
    """Compact list for the scenario table ('Multiplier 2,50; Caution 0,80')."""
    d = base_params(params).diff(params)
    return "; ".join(f"{param_label(k, lang)} {param_value(k, b, lang)}" for k, (_a, b) in d.items()
                     if k not in DATA_KEYS)


# ---------------------------------------------------------------------------
# Results table helpers
# ---------------------------------------------------------------------------
def change_bucket(cur: np.ndarray, new: np.ndarray) -> np.ndarray:
    """UX 3.2 buckets of the change vs the current limit."""
    cur = np.asarray(cur, float)
    new = np.asarray(new, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(cur > 0, (new - cur) / cur, 0.0)
    return np.select(
        [(cur > 0) & (new <= 0), (cur <= 0) & (new > 0), (cur <= 0) & (new <= 0),
         rel <= -0.5, rel < -0.2, rel <= 0.2, rel < 0.5],
        ["TO_ZERO", "FROM_ZERO", "WITHIN_20", "DOWN_50", "DOWN_20_50", "WITHIN_20", "UP_20_50"],
        "UP_50").astype(object)


def over_text(cur: bool, new: bool, lang: str) -> str:
    """'No → Yes', 'Yes → No', or one word if unchanged."""
    y, n = TX.T("yes", lang), TX.T("no", lang)
    a, b = (y if cur else n), (y if new else n)
    return a if a == b else f"{a} → {b}"


def flags(row: pd.Series, lang: str) -> str:
    out = []
    if row["plausibility_flag"]:
        out.append(TX.T("flag_review", lang))
    if row["approval_needed"]:
        out.append(TX.T("flag_approval", lang, t=int(row["tier"])))
    if row["days_capped"]:
        out.append(TX.T("flag_late", lang))
    if row["is_exempt"]:
        out.append(TX.T("flag_exempt", lang))
    pct = row.get("behaviour_pct", 0.0)
    if pct > 0 or pct < 0:
        out.append(TX.T("flag_bonus" if pct > 0 else "flag_malus", lang))
    if bool(row.get("revenue_check_flag", False)):
        out.append(TX.T("flag_new_customer", lang))
    return " · ".join(out)


def text_values(row: pd.Series, p: Params) -> dict[str, Any]:
    from core.explain import text_values as tv
    v = tv(row, p)
    v["mult"] = p.multiplier
    return v


def reason_short(row: pd.Series, p: Params, lang: str) -> str:
    return TX.t(TX.REASON_TEXTS, row["reason_code"], lang, **text_values(row, p))


def reason_long(row: pd.Series, p: Params, lang: str) -> str:
    code = row["reason_code"]
    if code == "R_COEF_NOT_IN_CERVED" and bool(row["is_exempt"]):
        code = "R_COEF_NOT_IN_CERVED_EXEMPT"   # monitoring limit of an exempt class, neutral wording
    return TX.t(TX.REASON_LONG_TEXTS, code, lang, **text_values(row, p))


def why_change(row: pd.Series, p: Params, lang: str) -> str:
    return TX.t(TX.CHANGE_TEXTS, row["change_code"], lang, **text_values(row, p))


TABLE_MAIN = ["code", "name", "cur", "new", "diff", "over", "reason"]
TABLE_MORE = ["score", "age", "exposure", "overdue", "why", "flags"]


def customer_table(res: pd.DataFrame, p: Params, lang: str) -> pd.DataFrame:
    """The Results table (UX 3.3): numeric columns stay numeric for sorting.

    Main columns (``TABLE_MAIN``) fit a 1366 px screen; ``TABLE_MORE`` are shown on request.
    """
    rows = res
    vals = [text_values(r, p) for _, r in rows.iterrows()]
    reason = [TX.t(TX.REASON_TEXTS, c, lang, **v) for c, v in zip(rows["reason_code"], vals)]
    why = [TX.t(TX.CHANGE_TEXTS, c, lang, **v) for c, v in zip(rows["change_code"], vals)]
    out = pd.DataFrame({
        "code": rows["code"].values,
        "name": rows["name"].values,
        "cur": rows["current_limit"].values,
        "new": rows["proposed_limit"].values,
        "diff": rows["diff"].values,
        "over": [over_text(a, b, lang) for a, b in zip(rows["over_current"], rows["over_new"])],
        "reason": reason,
        "score": [score_label(b, lang) for b in rows["score_bucket"]],
        "age": [age_label(b, lang) if p.age_bands_enabled else "-" for b in rows["age_band"]]
        if "age_band" in rows else ["-"] * len(rows),
        "exposure": rows["exposure"].values,
        "overdue": rows["overdue"].values,
        "why": why,
        "flags": [flags(r, lang) for _, r in rows.iterrows()],
    })
    return out


# ---------------------------------------------------------------------------
# Customer page: the fixed 10-step table (UX 4.1)
# ---------------------------------------------------------------------------
def behaviour_calc(row: pd.Series, p: Params, lang: str) -> str:
    """Calculation text of the payment-behaviour step (delay = measured days - terms)."""
    band = row["behaviour_band"]
    if band == "NONE":
        return TX.T("st_beh_calc_none", lang)
    if band == "NEW_CUSTOMER":
        return TX.T("st_beh_calc_new", lang, new=num(p.new_customer_months, lang))
    if band == "FEW_INVOICES":
        return TX.T("st_beh_calc_few", lang, n=num(row.get("behaviour_invoices_n", 0), lang),
                    min=num(p.behaviour_min_invoices, lang))
    dd = lambda x: TX.render("{x:dd}", lang, x=x)  # noqa: E731
    kw = dict(delay=TX.render("{x:sdd}", lang, x=row["delay_days"]), meas=dd(row["days_measured"]),
              terms=dd(row["days_terms"]), tol=num(p.behaviour_tolerance_days, lang),
              full=num(p.behaviour_full_malus_days, lang), before=num(row["limit_after_coef"], lang),
              pct=pct(abs(float(row["behaviour_pct"])), lang, 1).replace(",0%", "%").replace(".0%", "%"))
    key = {"BONUS": "st_beh_calc_bonus", "TOLERANCE": "st_beh_calc_tol"}.get(band, "st_beh_calc_malus")
    return TX.T(key, lang, **kw)


def step_rows(row: pd.Series, p: Params, lang: str) -> list[dict[str, Any]]:
    """Ten rows + total, same shape for every customer (eleven with the payment bonus / malus:
    step 7 is the behaviour step and the later ones move by one).

    Each row: {"n", "step", "calc", "amount" (float | None), "ron" (text)}. Rows after a rule
    that sets the limit to 0 show "-". The last numeric amount always equals the proposed limit.
    """
    L = lambda k, **kw: TX.T(k, lang, **kw)  # noqa: E731
    A = lambda x: num(x, lang)  # noqa: E731
    rows: list[dict[str, Any]] = []

    def add(n: Any, step: str, calc: str, amount: Any = None, dash: bool = False) -> None:
        rows.append({"n": str(n), "step": step, "calc": calc,
                     "amount": None if dash or amount is None else float(amount),
                     "ron": "-" if dash else ("" if amount is None else A(amount))})

    t12 = float(row["turnover_12m"])
    add(1, L("st_1"), L("st_1_calc"), t12)
    if annualised(row, p):   # v3.2: new / young customer, turnover divided by the months active
        monthly = float(row["monthly_revenue_used"])
        add(2, L("st_2"), L("st_2_calc_age", t12=A(t12), months=TX.render("{x:dd}", lang, x=row["months_active"]),
                            band=age_label(row["age_band"], lang).lower()), monthly)
    else:
        monthly = t12 / 12
        add(2, L("st_2"), L("st_2_calc", t12=A(t12)), monthly)

    src = {"measured": "st_3_src_measured", "terms": "st_3_src_terms",
           "contractual": "st_3_src_contract"}.get(row["days_source"], "st_3_src_default")
    meas = row["days_raw"]
    if p.m1_days_basis == "contractual":
        calc3 = L("st_3_calc_contract", src=L(src), meas=A(meas), min=A(p.min_days), used=A(row["days_used"]))
    elif p.cap_days_enabled:
        terms_cap = float(row["days_max"]) - p.cap_extra_days  # terms, at least the minimum days
        calc3 = L("st_3_calc", src=L(src), meas=A(meas), min=A(p.min_days), terms=A(terms_cap),
                  over=A(p.cap_extra_days), max=A(row["days_max"]), used=A(row["days_used"]))
    else:
        calc3 = L("st_3_calc_nocap", src=L(src), meas=A(meas), min=A(p.min_days), used=A(row["days_used"]))
    add(3, L("st_3"), calc3)

    m_shown = max(monthly, 0.0)
    add(4, L("st_4"), L("st_4_calc", m=A(m_shown), used=A(row["days_used"]), buf=pct(p.buffer, lang)), row["m1"])
    zeroed = float(row["m1"]) <= 0

    score = score_label(row["score_bucket"], lang)
    if bool(row["is_exempt"]) and row["score_bucket"] == "NONE":
        score = L("st_6_exempt", score=score)
    o = 1 if p.behaviour_enabled else 0   # the payment-behaviour step moves the later ones by one
    if zeroed:
        add(5, L("st_5", mult=TX.render("{m:x}", lang, m=p.multiplier)), "-", dash=True)
        add(6, L("st_6", score=score), "-", dash=True)
        if o:
            add(7, L("st_beh", band=L("beh_" + str(row["behaviour_band"]))), "-", dash=True)
        add(7 + o, L("st_7"), "-", dash=True)
    else:
        add(5, L("st_5", mult=TX.render("{m:x}", lang, m=p.multiplier)),
            L("st_5_calc", mult=coef(p.multiplier, lang), m1=A(row["m1"])), row["base_limit"])
        add(6, L("st_6", score=score), L("st_6_calc", base=A(row["base_limit"]), coef=coef(row["coefficient"], lang)),
            row["limit_after_coef"])
        if o:
            add(7, L("st_beh", band=L("beh_" + str(row["behaviour_band"]))), behaviour_calc(row, p, lang),
                row["limit_after_behaviour"], dash=float(row["limit_after_coef"]) <= 0)
        zeroed = float(row["limit_after_coef"]) <= 0
        if zeroed:
            add(7 + o, L("st_7"), "-", dash=True)
        elif not p.cerved_cap_enabled:
            add(7 + o, L("st_7"), L("st_7_calc_off"), row["limit_after_ceiling"])
        elif pd.isna(row["ceiling"]) and bool(row["in_cerved"]) and pd.notna(row["cerved_limit_orig"]) \
                and not bool(row["cerved_limit_usable"]):
            cur = row["cerved_currency"] if isinstance(row["cerved_currency"], str) else CO.currency()
            add(7 + o, L("st_7"), L("st_7_calc_invalid", amt=f"{A(row['cerved_limit_orig'])} {cur}"),
                row["limit_after_ceiling"])
        elif pd.isna(row["ceiling"]):
            add(7 + o, L("st_7"), L("st_7_calc_none"), row["limit_after_ceiling"])
        elif bool(row["ceiling_binds"]):
            add(7 + o, L("st_7"), L("st_7_calc_applies", amt=A(row["ceiling_unit"])), row["limit_after_ceiling"])
            zeroed = float(row["limit_after_ceiling"]) <= 0
        else:
            add(7 + o, L("st_7"), L("st_7_calc_no", amt=A(row["ceiling_unit"])), row["limit_after_ceiling"])

    if bool(row["zero_special"]):
        add(8 + o, L("st_8"), L("st_8_calc_special", cls=row["risk_class"]), 0.0)
        zeroed = True
    elif bool(row["zero_no_turnover"]):
        add(8 + o, L("st_8"), L("st_8_calc_noturn"), 0.0)
        zeroed = True
    elif zeroed:
        add(8 + o, L("st_8"), "-", dash=True)
    else:
        add(8 + o, L("st_8"), L("not_applicable"), row["limit_before_rounding"])

    final = float(row["proposed_limit"])
    rounded = float(row["limit_rounded"])
    step_txt = A(p.rounding_step)
    raw_min = 0 < rounded < p.min_limit
    hard = bool(row["hard_cap_applied"])
    if zeroed or float(row["limit_before_rounding"]) <= 0:
        add(9 + o, L("st_9"), "-", dash=True)
        add(10 + o, L("st_10"), "-", dash=True)
    else:
        if hard and not raw_min:
            add(9 + o, L("st_9"), L("st_9_calc_hard", up=A(rounded), ceil=A(row["ceiling_unit"]), step=step_txt,
                                final=A(final)), final)
        else:
            key9 = "st_9_calc_up" if p.rounding_mode == "up" else "st_9_calc_down"
            add(9 + o, L("st_9"), L(key9, step=step_txt), rounded)
        if rounded <= 0:
            add(10 + o, L("st_10"), "-", dash=True)
        elif hard and 0 < final < p.min_limit:
            add(10 + o, L("st_10"), L("st_10_calc_capped", min=A(p.min_limit), ceil=A(row["ceiling_unit"]),
                                  final=A(final)), final)
        elif raw_min:
            add(10 + o, L("st_10"), L("st_10_calc_applies", min=A(p.min_limit)), final)
        else:
            add(10 + o, L("st_10"), L("st_10_calc_no", min=A(p.min_limit)), final)
    add("", L("st_total"), "", final)
    return rows


# ---------------------------------------------------------------------------
# Data page: quality table (UX 2, 6.4)
# ---------------------------------------------------------------------------
FINDING_ROWS = {  # core finding code -> copy-deck key (meaning = key + "_m")
    "AR_TOTAL_ROWS_DROPPED": "dq_total_rows", "CV_DUP_CODE": "dq_dup_codes",
    "MATCH_VAT_DIFFERS": "dq_vat_mismatch", "CV_NO_CODE": "dq_no_ref", "CV_EUR_LIMIT": "dq_cerved_eur",
    "CV_UNMATCHED": "dq_unmatched", "CF_LIMIT_BLANK": "dq_limit_blank", "CF_NO_CODE": "dq_cf_no_code",
    "CF_DUP_CODE": "dq_cf_dup_code", "CV_NO_CURRENCY": "dq_no_currency",
    "CV_UNKNOWN_SCORE": "dq_unknown_score", "AR_NO_INVOICE_DATE": "dq_no_invoice_date",
    "MATCH_VAT_CONFLICT": "dq_vat_conflict", "CV_OTHER_CURRENCY": "dq_other_currency",
    "CV_NEGATIVE_LIMIT": "dq_negative_limit", "CF_MULTI_COMPANY": "dq_multi_company",
    "COLUMN_MISSING": "dq_column_missing", "BAD_NUMBERS": "dq_bad_numbers", "BAD_DATES": "dq_bad_dates",
    "FILE_EMPTY": "dq_file_empty", "AMBIGUOUS_NUMBERS": "dq_ambiguous_numbers",
    "MD_NO_CODE": "dq_md_no_code", "MD_DUP_CODE": "dq_md_dup_code",
    # parameter / result dependent (v3.2 customer age): engine.coverage_finding / engine.age_findings
    "AR_SHORT_HISTORY": "dq_ar_short_history", "AGE_INVOICE_BEFORE_OPENING": "dq_age_before_opening",
    "MD_CUSTOMER_MISSING": "dq_md_missing",
}


def _finding_values(f: Any, lang: str) -> dict[str, str]:
    """Placeholders for the meaning sentence of the new findings (already formatted)."""
    d = f.details
    cols = d.get("columns")
    return {
        "rematched": num(d.get("rematched_by_vat", 0), lang), "none": num(d.get("not_in_cerved", 0), lang),
        "currencies": str(d.get("currencies", "")),
        "kept": f"{d.get('kept', '?')} {d.get('kept_name') or ''}".strip(),
        "companies": "; ".join(f.examples) if f.code == "CF_MULTI_COMPANY" else "",
        "columns": ", ".join(cols) if isinstance(cols, list) else ", ".join(f"{k} ({v})" for k, v in (cols or {}).items()),
        "features": ", ".join(TX.UNAVAILABLE_TEXTS.get(x, {}).get(lang, x) for x in d.get("unavailable", [])) or "-",
        "examples": "; ".join(map(str, f.examples[:3])),
        "files": ", ".join(map(str, f.examples)),
        "months": TX.render("{x:dd}", lang, x=d.get("months")) if d.get("months") is not None else "-",
        "needed": num(d.get("needed"), lang), "scope_n": num(d.get("scope_n", 0), lang),
    }


def quality_checks(data: LoadedData, res: pd.DataFrame | None, p: Params,
                   lang: str) -> list[dict[str, Any]]:
    """Rows of the quality table: {key, check, count, meaning, rows (DataFrame | None), examples}."""
    L = lambda k, **kw: TX.T(k, lang, **kw)  # noqa: E731
    out: list[dict[str, Any]] = []
    cv = data.cerved
    cust = data.matched_customers(p.cerved_reject_vat_conflict)   # the matching rule actually used

    def cv_rows(mask: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({L("dq_c_code"): cv.loc[mask, "code"].fillna("-").values,
                             L("dq_c_name"): cv.loc[mask, "name"].values,
                             L("dq_c_vat"): cv.loc[mask, "vat"].values})

    def res_rows(mask: pd.Series, extra: dict[str, pd.Series] | None = None) -> pd.DataFrame:
        d = {L("dq_c_code"): res.loc[mask, "code"].values, L("dq_c_name"): res.loc[mask, "name"].values,
             L("dq_c_vat"): res.loc[mask, "vat"].values}
        for k, s in (extra or {}).items():
            d[k] = s[mask].values
        return pd.DataFrame(d)

    from core.engine import age_findings, coverage_finding
    extra = [coverage_finding(data, p)] + (age_findings(res, data, p) if res is not None else [])
    for f in list(data.findings_for(p.cerved_reject_vat_conflict)) + [x for x in extra if x is not None]:
        key = FINDING_ROWS.get(f.code)
        if key is None or f.count <= 0:
            continue
        rows = None
        meaning = L(key + "_m", rate=TX.fmt_amount(p.eur_rate, lang, 3), **_finding_values(f, lang))
        if f.code == "CV_DUP_CODE" and cv is not None:
            codes = set(f.examples) if len(f.examples) >= f.count else set(
                cv.loc[cv["code"].duplicated(keep=False) & cv["code"].notna(), "code"])
            rows = cv_rows(cv["code"].isin(codes)).sort_values(L("dq_c_code"))
        elif f.code == "MATCH_VAT_DIFFERS" and cust is not None:
            m = cust["vat_differs"]
            rows = pd.DataFrame({L("dq_c_code"): cust.loc[m, "code"].values, L("dq_c_name"): cust.loc[m, "name"].values,
                                 L("dq_c_vat"): cust.loc[m, "vat"].values,
                                 L("dq_c_cv_name"): cust.loc[m, "cv_name"].values,
                                 L("dq_c_cv_vat"): cust.loc[m, "cv_vat"].values})
        elif f.code == "CV_NO_CODE" and cv is not None:
            rows = cv_rows(cv["code"].isna())
        elif f.code == "CV_EUR_LIMIT" and cv is not None:
            m = cv["currency"].eq("EUR") & cv["cerved_limit"].notna()
            rows = cv_rows(m)
            rows[L("dq_c_value")] = [f"{num(x, lang)} EUR" for x in cv.loc[m, "cerved_limit"]]
        elif f.code == "CV_UNMATCHED" and cv is not None:
            idx = set(f.details.get("rows", []))
            rows = cv_rows(cv["cv_row"].isin(idx))
        elif f.code == "MATCH_VAT_CONFLICT" and cust is not None:
            m = cust["vat_conflict"]
            rows = pd.DataFrame({L("dq_c_code"): cust.loc[m, "code"].values, L("dq_c_name"): cust.loc[m, "name"].values,
                                 L("dq_c_vat"): cust.loc[m, "vat"].values,
                                 L("dq_c_cv_name"): cust.loc[m, "conflict_cv_name"].values,
                                 L("dq_c_cv_vat"): cust.loc[m, "conflict_cv_vat"].values})
        elif f.code in ("CV_OTHER_CURRENCY", "CV_NEGATIVE_LIMIT") and cv is not None:
            lim = cv["cerved_limit"].notna()
            m = (cv["cerved_limit"] < 0) & lim if f.code == "CV_NEGATIVE_LIMIT" else \
                lim & cv["currency"].notna() & ~cv["currency"].isin([CO.currency(), "EUR"])
            rows = cv_rows(m)
            rows[L("dq_c_value")] = [f"{num(x, lang)} {c if isinstance(c, str) else ''}".strip()
                                     for x, c in cv.loc[m, ["cerved_limit", "currency"]].values]
        elif f.code in ("CF_LIMIT_BLANK",) and res is not None:
            rows = res_rows(res["code"].isin(set(f.examples)))
        elif f.code in ("AGE_INVOICE_BEFORE_OPENING", "MD_CUSTOMER_MISSING") and res is not None:
            m = res["code"].isin(set(f.details.get("codes", [])))
            rows = res_rows(m, {L("dq_c_opened"): res["opened_date"].map(date_str),
                                L("dq_c_first_inv"): res["first_invoice_date"].map(date_str)})
        out.append({"key": key, "check": L(key), "count": int(f.count), "meaning": meaning,
                    "rows": rows, "examples": list(f.examples)})
        if f.code == "CV_DUP_CODE":
            diff = list(f.details.get("codes_with_different_vat", []))
            if diff and cv is not None:
                ex = []
                for c in diff[:3]:
                    names = cv.loc[cv["code"] == c, "name"].fillna("?").tolist()
                    ex.append(f"{c} ({' / '.join(n.split()[0] if n else '?' for n in names)})")
                out.append({"key": "dq_dup_diff_company", "check": L("dq_dup_diff_company"),
                            "count": len(diff), "meaning": L("dq_dup_diff_company_m", examples=", ".join(ex)),
                            "rows": cv_rows(cv["code"].isin(set(diff))).sort_values(L("dq_c_code")),
                            "examples": diff})
    if res is not None:
        m = res["turnover_12m"] < 0
        if m.any():
            out.append({"key": "dq_neg_turnover", "check": L("dq_neg_turnover"), "count": int(m.sum()),
                        "meaning": L("dq_neg_turnover_m"),
                        "rows": res_rows(m, {L("dq_c_value"): res["turnover_12m"].map(lambda x: num(x, lang))}),
                        "examples": []})
        if data.ar is not None:
            m = res["n_invoices"] <= 0
            if m.any():
                out.append({"key": "dq_no_invoices", "check": L("dq_no_invoices"), "count": int(m.sum()),
                            "meaning": L("dq_no_invoices_m", days=num(p.fallback_days, lang)),
                            "rows": res_rows(m), "examples": []})
        m = res["current_limit"] <= 0
        if m.any():
            out.append({"key": "dq_no_current_limit", "check": L("dq_no_current_limit"), "count": int(m.sum()),
                        "meaning": L("dq_no_current_limit_m"), "rows": res_rows(m), "examples": []})
    return out


def file_error(f: Any, lang: str) -> str:
    """Translated message for a FILE_INVALID / FILE_DUPLICATE_KIND finding."""
    name = f.examples[0] if f.examples else "?"
    kinds = {"checkfidi": TX.T("file_checkfidi", lang), "cerved": TX.T("file_cerved", lang),
             "ar124": TX.T("file_ar124", lang), "md105": TX.T("file_md105", lang)}
    if f.code == "FILE_DUPLICATE_KIND":
        return TX.T("err_duplicate_kind", lang, name=name, kind=kinds.get(f.details.get("kind"), "?"),
                    kept=f.details.get("kept", "?"))
    msg = str(f.details.get("message", ""))
    m = re.search(r"looks like (\w+) but required column\(s\) are missing: (.*?)\. Columns found", msg)
    if m:
        return TX.T("err_missing_cols", lang, name=name, kind=kinds.get(m.group(1), m.group(1)),
                    cols=m.group(2).replace("'", ""))
    if "not recognised" in msg:
        return TX.T("err_unrecognised", lang, name=name)
    return TX.T("err_unreadable", lang, name=name)


# ---------------------------------------------------------------------------
# Rules page (UX 7.1)
# ---------------------------------------------------------------------------
def rules(p: Params, n_scope: int | None, lang: str,
          ref_date: Any = None) -> dict[str, list[tuple[str, bool]]]:
    """Sections -> list of (markdown sentence, changed vs v3). The "how" section lets anybody
    recompute a limit by hand: one-line formula, then the steps in order with where each input
    comes from."""
    b = base_params(p)
    L = lambda k, **kw: TX.T(k, lang, **kw)  # noqa: E731
    ch = lambda *keys: any(getattr(p, k) != getattr(b, k) for k in keys)  # noqa: E731
    bold = lambda key, txt: f"**{txt}**" if ch(key) else txt  # noqa: E731
    C2 = lambda x: coef(x, lang)  # noqa: E731

    def lst(key: str) -> str:
        v = getattr(p, key)
        return bold(key, ", ".join(v) if v else L("none_word"))

    ref = date_str(ref_date) if ref_date is not None else L("m_ref_date").lower()
    scope = L("rl_scope", n=num(n_scope, lang)) if n_scope is not None else L("rl_scope_nocount")
    who = [
        (L("rl_active"), False),
        (L("rl_intercompany", list=lst("intercompany_codes")), ch("intercompany_codes")),
        (L("rl_special", list=lst("special_classes")), ch("special_classes")),
        (L("rl_exempt", list=lst("exempt_classes"), enf=bold("coef_exempt_not_in_cerved",
                                                              C2(p.coef_exempt_not_in_cerved))),
         ch("exempt_classes", "coef_exempt_not_in_cerved")),
        (scope, ch("special_classes", "exempt_classes", "intercompany_codes")),
        (L("rl_exposure"), False),
        (L("rl_match_reject" if p.cerved_reject_vat_conflict else "rl_match_keep"), ch("cerved_reject_vat_conflict")),
    ]
    rdir = L("rl_round_up_word" if p.rounding_mode == "up" else "rl_round_down_word")
    mult_x = TX.render("{m:x}", lang, m=p.multiplier)
    fkw = dict(dir=bold("rounding_mode", rdir), step=bold("rounding_step", num(p.rounding_step, lang)),
               mult=bold("multiplier", mult_x), min=bold("min_limit", num(p.min_limit, lang)),
               buf=bold("buffer", pct(p.buffer, lang)),
               beh=bold("behaviour_enabled", L("rl_beh_formula")) if p.behaviour_enabled else "",
               div=bold("age_bands_enabled", L("rl_div_age")) if p.age_bands_enabled else "12")
    formula = (L("rl_formula", **fkw) if p.cerved_cap_enabled else L("rl_formula_nocap", **fkw),
               ch("rounding_mode", "rounding_step", "multiplier", "min_limit", "buffer", "cerved_cap_enabled",
                  "behaviour_enabled", "age_bands_enabled"))
    days_txt = L("rl_days", months=bold("window_months", num(p.window_months, lang)), ref=ref)
    if p.m1_days_basis == "contractual":   # M1 on the terms; the measured days only drive the bonus / malus
        d = [L("rl_days_basis_contract", min=bold("min_days", num(p.min_days, lang)),
               days=bold("fallback_days", num(p.fallback_days, lang))), days_txt]
    else:
        d = [days_txt]
        d.append(L("rl_days_min", min=bold("min_days", num(p.min_days, lang))))
        d.append(L("rl_days_cap", over=bold("cap_extra_days", num(p.cap_extra_days, lang)),
                   min=num(p.min_days, lang)) if p.cap_days_enabled else L("rl_days_nocap"))
        d.append(L("rl_days_default", days=bold("fallback_days", num(p.fallback_days, lang))))
    d.append(L("rl_terms_positive" if p.terms_positive_only else "rl_terms_all"))
    share = 1.0 / (p.multiplier * (1 + p.buffer)) if p.multiplier > 0 else float("nan")
    share_txt = pct(share, lang) if share == share else "-"
    if 0.4 <= share <= 0.6:
        share_txt = L("rl_share_half", pct=share_txt)
    coef_txt = L("rl_coef", r=bold("coef_reliable", C2(p.coef_reliable)),
                 c=bold("coef_caution", C2(p.coef_caution)),
                 mc=bold("coef_max_caution", C2(p.coef_max_caution)),
                 nf=bold("coef_not_in_cerved", C2(p.coef_not_in_cerved)),
                 enf=bold("coef_exempt_not_in_cerved", C2(p.coef_exempt_not_in_cerved)))
    if p.coef_max_caution == 0:
        coef_txt += " " + L("rl_max_caution_why")
    age_keys = ("age_bands_enabled", "new_customer_months", "consolidated_months")
    if p.age_bands_enabled:
        age_txt = (L("rl_age_on", new=bold("new_customer_months", num(p.new_customer_months, lang)),
                     cons=bold("consolidated_months", num(p.consolidated_months, lang))), ch(*age_keys))
    else:
        age_txt = (L("rl_age_off"), ch(*age_keys))
    limit = [
        (L("rl_t12"), False),
        age_txt,
        (" ".join(d), ch("window_months", "min_days", "cap_days_enabled", "cap_extra_days", "fallback_days",
                         "terms_positive_only", "m1_days_basis")),
        (L("rl_need", buf=bold("buffer", pct(p.buffer, lang)), div=fkw["div"]), ch("buffer", "age_bands_enabled")),
        (L("rl_mult", mult=bold("multiplier", mult_x), share=share_txt), ch("multiplier", "buffer")),
        (coef_txt, ch("coef_reliable", "coef_caution", "coef_max_caution", "coef_not_in_cerved",
                      "coef_exempt_not_in_cerved")),
    ]
    beh_keys = ("behaviour_enabled", "behaviour_bonus_max", "behaviour_malus_max", "behaviour_tolerance_days",
                "behaviour_full_malus_days")
    if p.behaviour_enabled:
        limit.append((L("rl_behaviour_on", bonus=bold("behaviour_bonus_max", pct(p.behaviour_bonus_max, lang)),
                        malus=bold("behaviour_malus_max", pct(p.behaviour_malus_max, lang)),
                        tol=bold("behaviour_tolerance_days", num(p.behaviour_tolerance_days, lang)),
                        full=bold("behaviour_full_malus_days", num(p.behaviour_full_malus_days, lang))),
                      ch(*beh_keys)))
        limit.append((L("rl_beh_min", n=bold("behaviour_min_invoices", num(p.behaviour_min_invoices, lang)),
                        months=bold("window_months", num(p.window_months, lang)))
                      if p.behaviour_min_invoices > 0 else L("rl_beh_min_off"), ch("behaviour_min_invoices")))
    else:
        limit.append((L("rl_behaviour_off"), ch(*beh_keys)))
    if p.cerved_cap_enabled:
        cap = L("rl_cap_on", rate=bold("eur_rate", TX.fmt_amount(p.eur_rate, lang, 3)))
        if p.ceiling_is_hard:
            cap += " " + L("rl_cap_hard")
        limit.append((cap, ch("cerved_cap_enabled", "eur_rate", "ceiling_is_hard")))
    else:
        limit.append((L("rl_cap_off"), True))
    limit += [
        (L("rl_zero"), False),
        (L("rl_round", dir=bold("rounding_mode", rdir),
           step=bold("rounding_step", num(p.rounding_step, lang))), ch("rounding_mode", "rounding_step")),
        (L("rl_min", min=bold("min_limit", num(p.min_limit, lang))), ch("min_limit")),
    ]
    checks = [
        (L("rl_over"), False),
        (L("rl_plaus", pct=bold("plausibility_threshold", pct(p.plausibility_threshold, lang))),
         ch("plausibility_threshold")),
        (L("rl_approval", pct=bold("approval_threshold", pct(p.approval_threshold, lang)),
           amt=bold("approval_min_change", num(p.approval_min_change, lang))),
         ch("approval_threshold", "approval_min_change")),
        (L("rl_tiers", t1=bold("tier1_eur", num(p.tier1_eur, lang)), t2=bold("tier2_eur", num(p.tier2_eur, lang)),
           rate=bold("eur_rate", TX.fmt_amount(p.eur_rate, lang, 3))), ch("tier1_eur", "tier2_eur", "eur_rate")),
    ]
    return {"rules_h_who": who, "rules_h_formula": [formula], "rules_h_limit": limit, "rules_h_checks": checks}


def rules_markdown(sections: dict[str, list[tuple[str, bool]]], lang: str) -> dict[str, str]:
    tag = f" *{TX.T('rules_changed_tag', lang)}*"
    return {h: "\n".join((f"{i}. " if len(items) > 1 else "") + f"{s}{tag if c else ''}"
                         for i, (s, c) in enumerate(items, 1))
            for h, items in sections.items()}


def rules_text(sections: dict[str, list[tuple[str, bool]]], lang: str) -> str:
    """Plain text version (for minutes)."""
    tag = " " + TX.T("rules_changed_tag", lang)
    parts = [TX.T("rules_title", lang), ""]
    for h, items in sections.items():
        parts.append(TX.T(h, lang).upper())
        for i, (s, c) in enumerate(items, 1):
            num_ = f"{i}. " if len(items) > 1 else ""
            parts.append(f"{num_}{s.replace('**', '').replace('*', '')}{tag if c else ''}")
        parts.append("")
    return "\n".join(parts)


GLOSSARY = ["g_exposure", "g_age", "g_m1", "g_mult", "g_coef", "g_cap", "g_scope", "g_over", "g_zero_rule",
            "g_plaus", "g_approval", "g_ic", "g_exempt", "g_monitor", "g_special", "g_days"]
