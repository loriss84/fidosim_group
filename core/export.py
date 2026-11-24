"""Excel export: customers (friendly column names), KPIs, parameters used."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import texts as T
from .country import localise
from .explain import add_texts
from .kpi import kpis
from .params import Params

EXPORT_COLUMNS = [
    "code", "name", "risk_class", "score_bucket", "in_cerved", "match_method", "cerved_limit_ron",
    "cerved_turnover", "balance", "overdue", "ordered", "delivered", "exposure", "turnover_12m",
    "days_measured", "days_terms", "days_used", "days_capped", "m1", "base_limit", "coefficient",
    "limit_after_coef", "ceiling", "limit_before_rounding", "current_limit", "proposed_limit", "diff",
    "diff_pct", "direction", "in_scope", "is_exempt", "is_special", "over_new", "over_current",
    "excess_new", "excess_current", "plausibility_ratio", "plausibility_flag", "approval_needed",
    "tier", "reason", "why_change", "reason_code", "change_code",
]

# payment-behaviour columns, written after "limit_after_coef" only when the option is on (the default
# workbook stays as it was)
BEHAVIOUR_COLUMNS = ["delay_days", "behaviour_band", "behaviour_pct", "limit_after_behaviour",
                     "proposed_limit_no_behaviour", "behaviour_effect"]
# customer-age columns (v3.2), written before "m1" when the age bands or the minimum-invoices gate are on
AGE_COLUMNS = ["opened_date", "first_invoice_date", "age_start_date", "age_source", "age_months", "age_censored", "age_band",
               "months_active", "monthly_revenue_used", "behaviour_invoices_n", "revenue_check_flag"]
DATE_COLUMNS = ("opened_date", "first_invoice_date", "age_start_date")
PERCENT_COLUMNS = ("diff_pct", "plausibility_ratio", "behaviour_pct")   # fractions shown as percentages
SHARE_KPIS = {"in_cerved_exposure_share_active"}       # KPI values that are fractions (shown as %)


def to_excel(result: pd.DataFrame, params: Params, lang: str = "it",
             path: str | Path | None = None) -> bytes:
    """Write the workbook; return its bytes (and save to ``path`` if given)."""
    li = 0 if lang == "it" else 1
    cols = export_columns(params)
    df = add_texts(result, params, lang)[cols].copy()
    # Cerved values in whole RON, as the proposed limit uses them (4.582,72 -> 4.582)
    df["ceiling"] = result["ceiling_unit"].values
    df["cerved_limit_ron"] = np.floor(np.round(result["cerved_limit_ron"].to_numpy(dtype=float), 6))
    df["match_method"] = df["match_method"].map(
        lambda m: T.MATCH_TEXTS.get(m, {}).get(lang, m) if isinstance(m, str) else T.MATCH_TEXTS["none"][lang])
    df["score_bucket"] = df["score_bucket"].map(lambda b: T.SCORE_TEXTS.get(b, {}).get(lang, b))
    df["direction"] = df["direction"].map(lambda d: T.DIRECTION_TEXTS.get(d, {}).get(lang, d))
    if "age_band" in df:
        df["age_band"] = df["age_band"].map(lambda b: T.AGE_BAND_TEXTS.get(b, {}).get(lang, b))
        df["age_source"] = df["age_source"].map(
            lambda b: T.AGE_SOURCE_TEXTS.get(b, {}).get(lang, b) if isinstance(b, str) else None)
        df["age_months"] = df["age_months"].round(1)
        for c in DATE_COLUMNS:   # dates without time (dd/mm/yyyy in the workbook)
            df[c] = pd.to_datetime(df[c]).dt.normalize()
    if "behaviour_band" in df:
        df["behaviour_band"] = df["behaviour_band"].map(lambda b: T.BAND_TEXTS.get(b, {}).get(lang, b))
    df = df.replace([np.inf, -np.inf], np.nan)
    df.columns = [localise(T.COLUMN_TEXTS.get(c, (c, c))[li]) for c in df.columns]

    k = kpis(result)
    kdf = pd.DataFrame({T.EXPORT_TEXTS["col_kpi"][lang]: [localise(T.KPI_TEXTS.get(x, {}).get(lang, x)) for x in k],
                        "key": list(k), T.EXPORT_TEXTS["col_value"][lang]: list(k.values())})
    pd_ = params.to_dict()
    pdf = pd.DataFrame({T.EXPORT_TEXTS["col_param"][lang]:
                        [_param_label(x, lang) for x in pd_],
                        "key": list(pd_),
                        T.EXPORT_TEXTS["col_value"][lang]: [_cell(v) for v in pd_.values()]})

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="dd/mm/yyyy", date_format="dd/mm/yyyy") as xw:
        for name, frame in ((T.EXPORT_TEXTS["sheet_customers"][lang], df),
                            (T.EXPORT_TEXTS["sheet_kpi"][lang], kdf),
                            (T.EXPORT_TEXTS["sheet_params"][lang], pdf)):
            frame.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes(1, 0)
            for i, col in enumerate(frame.columns):
                ws.set_column(i, i, min(max(len(str(col)), 10) + 2, 45))
        # KPI sheet: shares as percentages, other values as numbers
        ws = xw.sheets[T.EXPORT_TEXTS["sheet_kpi"][lang]]
        f_pct = xw.book.add_format({"num_format": "0.0%"})
        f_num = xw.book.add_format({"num_format": "#,##0"})
        for i, key in enumerate(k):
            ws.write_number(i + 1, 2, float(k[key]), f_pct if key in SHARE_KPIS else f_num)
        ws = xw.sheets[T.EXPORT_TEXTS["sheet_customers"][lang]]
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        num = xw.book.add_format({"num_format": "#,##0"})
        pct = xw.book.add_format({"num_format": "0.0%"})
        for i, c in enumerate(cols):
            if c in ("limit_after_behaviour", "proposed_limit_no_behaviour", "behaviour_effect", "balance", "overdue", "ordered", "delivered", "exposure", "turnover_12m", "m1",
                     "base_limit", "limit_after_coef", "ceiling", "limit_before_rounding",
                     "current_limit", "proposed_limit", "diff", "excess_new", "excess_current",
                     "cerved_limit_ron", "cerved_turnover", "monthly_revenue_used"):
                ws.set_column(i, i, 16, num)
            elif c in PERCENT_COLUMNS:
                ws.set_column(i, i, 14, pct)
    data = buf.getvalue()
    if path is not None:
        Path(path).write_bytes(data)
    return data


def export_columns(params: Params) -> list[str]:
    """Customer-sheet columns: EXPORT_COLUMNS, plus the customer-age ones before M1 (age bands or the
    minimum-invoices gate on) and the payment-behaviour ones after the risk factor (bonus / malus on)."""
    cols = list(EXPORT_COLUMNS)
    if params.behaviour_enabled:
        i = cols.index("limit_after_coef") + 1
        cols = cols[:i] + BEHAVIOUR_COLUMNS + cols[i:]
    if params.age_bands_enabled or params.behaviour_min_invoices > 0:
        i = cols.index("m1")
        cols = cols[:i] + AGE_COLUMNS + cols[i:]
    return cols


def _cell(v: Any) -> Any:
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return "" if v is None else v


def _param_label(key: str, lang: str) -> str:
    """Label from texts.PARAM_TEXTS (str or {"label": ...}) if the UI agent filled it, else the key."""
    e = T.PARAM_TEXTS.get(key, {}).get(lang)
    if isinstance(e, dict):
        return localise(str(e.get("label", key)))
    return localise(str(e)) if e else key
