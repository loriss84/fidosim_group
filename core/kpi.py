"""KPIs of a simulation result, scenario comparison, data-page summary.

KPIs are computed on the order-control perimeter (``in_scope``) unless the key ends
with ``_active`` (all active, non-intercompany customers). Amounts in RON.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .engine import AGE_BANDS, BUCKETS, reference_date
from .loaders import LoadedData
from .params import Params

AGE_KEYS = {"NEW": "new", "YOUNG": "young", "CONSOLIDATED": "consolidated", "NO_HISTORY": "no_history"}
BUCKET_KEYS = {"AFFIDABILE": "reliable", "CAUTELA": "caution", "MASSIMA CAUTELA": "max_caution",
               "NONE": "not_in_cerved"}

# Stable KPI keys in display order (texts.KPI_TEXTS has a label for each).
KPI_KEYS = [
    "n_active", "n_scope",
    "limits_current_active", "limits_proposed_active", "exposure_active",
    "limits_current_scope", "limits_proposed_scope", "exposure_scope",
    "over_new_n", "over_current_n", "excess_new", "excess_current",
    "over_new_positive_n", "over_new_zero_n", "over_current_positive_n", "over_current_zero_n",
    "higher_n", "lower_n", "equal_n",
    "zero_with_turnover_n_active",
    "orders_over_new_n", "orders_over_current_n",
    "plausibility_n", "plausibility_exposure",
    "in_cerved_n_active", "in_cerved_exposure_share_active",
    "approval_n", "approval_tier1_n", "approval_tier2_n", "approval_tier3_n",
    "days_capped_n",
    "behaviour_bonus_n", "behaviour_tolerance_n", "behaviour_malus_n", "behaviour_no_history_n",
    "behaviour_effect_active", "behaviour_effect_scope", "behaviour_new_n", "behaviour_few_n",
] + [f"age_{a}_n" for a in AGE_KEYS.values()] + [f"{m}_{b}" for b in BUCKET_KEYS.values() for m in ("n", "over_new_n", "over_current_n")]


def kpis(result: pd.DataFrame) -> dict[str, float]:
    """KPI set of SPEC section 4 as a flat dict with stable keys (see KPI_KEYS)."""
    a = result
    s = a[a["in_scope"]]
    k: dict[str, float] = {}
    k["n_active"] = len(a)
    k["n_scope"] = len(s)
    k["limits_current_active"] = float(a["current_limit"].sum())
    k["limits_proposed_active"] = float(a["proposed_limit"].sum())
    k["exposure_active"] = float(a["exposure"].sum())
    k["limits_current_scope"] = float(s["current_limit"].sum())
    k["limits_proposed_scope"] = float(s["proposed_limit"].sum())
    k["exposure_scope"] = float(s["exposure"].sum())
    k["over_new_n"] = int(s["over_new"].sum())
    k["over_current_n"] = int(s["over_current"].sum())
    k["excess_new"] = float(s["excess_new"].sum())
    k["excess_current"] = float(s["excess_current"].sum())
    # over limit split: over a positive limit vs at limit 0 (by rule: maximum caution, Cerved 0,
    # no turnover, risk factor 0...; for today's limits: 0 in CreditBoard)
    pos_new, pos_cur = s["proposed_limit"] > 0, s["current_limit"] > 0
    k["over_new_positive_n"] = int((s["over_new"] & pos_new).sum())
    k["over_new_zero_n"] = int((s["over_new"] & ~pos_new).sum())
    k["over_current_positive_n"] = int((s["over_current"] & pos_cur).sum())
    k["over_current_zero_n"] = int((s["over_current"] & ~pos_cur).sum())
    k["higher_n"] = int(s["direction"].eq("HIGHER").sum())
    k["lower_n"] = int(s["direction"].eq("LOWER").sum())
    k["equal_n"] = int(s["direction"].eq("EQUAL").sum())
    k["zero_with_turnover_n_active"] = int(((a["proposed_limit"] == 0) & (a["turnover_12m"] > 0)
                                            & ~a["is_special"]).sum())
    k["orders_over_new_n"] = int((s["over_new"] & (s["ordered"] > 0)).sum())
    k["orders_over_current_n"] = int((s["over_current"] & (s["ordered"] > 0)).sum())
    k["plausibility_n"] = int(s["plausibility_flag"].sum())
    k["plausibility_exposure"] = float(s.loc[s["plausibility_flag"], "exposure"].sum())
    k["in_cerved_n_active"] = int(a["in_cerved"].sum())
    tot = a["exposure"].sum()
    k["in_cerved_exposure_share_active"] = float(a.loc[a["in_cerved"], "exposure"].sum() / tot) if tot else 0.0
    ap = s[s["approval_needed"]]
    k["approval_n"] = len(ap)
    for t in (1, 2, 3):
        k[f"approval_tier{t}_n"] = int((ap["tier"] == t).sum())
    k["days_capped_n"] = int(s["days_capped"].sum())
    # payment behaviour (0 when the option is off): customers in scope with a bonus / malus, and the
    # net effect of the bonus / malus on the total proposed limits (limit with - limit without)
    pct = s["behaviour_pct"] if "behaviour_pct" in s else pd.Series(0.0, index=s.index)
    k["behaviour_bonus_n"] = int((pct > 0).sum())
    k["behaviour_malus_n"] = int((pct < 0).sum())
    k["behaviour_tolerance_n"] = int(s["behaviour_band"].eq("TOLERANCE").sum()) if "behaviour_band" in s else 0
    # no payment history: no measured days (or no terms) -> no delay, never a bonus / malus
    k["behaviour_no_history_n"] = int(s["delay_days"].isna().sum()) if "delay_days" in s else 0
    eff = "behaviour_effect"
    k["behaviour_effect_active"] = float(a[eff].sum()) if eff in a else 0.0
    k["behaviour_effect_scope"] = float(s[eff].sum()) if eff in s else 0.0
    # v3.2: bonus / malus not applied (new customer / too few invoices due), customers by age band
    bb = s["behaviour_band"] if "behaviour_band" in s else pd.Series("NONE", index=s.index)
    k["behaviour_new_n"] = int(bb.eq("NEW_CUSTOMER").sum())
    k["behaviour_few_n"] = int(bb.eq("FEW_INVOICES").sum())
    ab = s["age_band"] if "age_band" in s else pd.Series("NO_HISTORY", index=s.index)
    for band, key in AGE_KEYS.items():
        k[f"age_{key}_n"] = int(ab.eq(band).sum())
    for bucket, key in BUCKET_KEYS.items():
        sb = s[s["score_bucket"] == bucket]
        k[f"n_{key}"] = len(sb)
        k[f"over_new_n_{key}"] = int(sb["over_new"].sum())
        k[f"over_current_n_{key}"] = int(sb["over_current"].sum())
    return {key: k[key] for key in KPI_KEYS}


def score_breakdown(result: pd.DataFrame) -> pd.DataFrame:
    """Perimeter split by Cerved score bucket: customers, exposure, limits, over limit."""
    s = result[result["in_scope"]]
    g = s.groupby("score_bucket")
    out = pd.DataFrame({
        "n": g.size(), "exposure": g["exposure"].sum(),
        "limits_current": g["current_limit"].sum(), "limits_proposed": g["proposed_limit"].sum(),
        "over_new_n": g["over_new"].sum(), "over_current_n": g["over_current"].sum(),
        "excess_new": g["excess_new"].sum(), "excess_current": g["excess_current"].sum(),
    }).reindex(BUCKETS).fillna(0)
    out.index.name = "score_bucket"
    return out.reset_index()


def age_breakdown(result: pd.DataFrame, scope: bool = True) -> pd.DataFrame:
    """Split by customer-age band (v3.2) of the perimeter (``scope=False``: all active customers):
    customers, exposure, current / proposed limits, over the new limit (total and over a positive limit),
    and the effect of the annualisation (limit with the turnover / months active minus turnover / 12 is
    not computed here: compare two results for that). Rows in ``AGE_BANDS`` order."""
    s = result[result["in_scope"]] if scope else result
    s = s.assign(_pos=s["over_new"] & (s["proposed_limit"] > 0))
    g = s.groupby("age_band")
    out = pd.DataFrame({
        "n": g.size(), "exposure": g["exposure"].sum(),
        "limits_current": g["current_limit"].sum(), "limits_proposed": g["proposed_limit"].sum(),
        "over_new_n": g["over_new"].sum(), "over_new_positive_n": g["_pos"].sum(),
        "over_current_n": g["over_current"].sum(),
    }).reindex(AGE_BANDS).fillna(0)
    out.index.name = "age_band"
    return out.reset_index()


def compare(base: dict[str, float], scenario: dict[str, float]) -> pd.DataFrame:
    """Table key / base / scenario / delta / delta_pct (delta_pct NaN when base is 0)."""
    rows = []
    for key in KPI_KEYS:
        b, s = base.get(key, np.nan), scenario.get(key, np.nan)
        d = s - b
        rows.append({"key": key, "base": b, "scenario": s, "delta": d,
                     "delta_pct": d / b if b not in (0, 0.0) and pd.notna(b) else np.nan})
    return pd.DataFrame(rows)


def changed_customers(base: pd.DataFrame, scenario: pd.DataFrame) -> pd.DataFrame:
    """Customers whose proposed limit or over-limit status differs between two results.

    ``change`` = 'LIMIT', 'OVER_STATUS' or 'BOTH'. Sorted by absolute limit change. A customer
    present in only one result (e.g. intercompany list changed) gets name, score, exposure and
    current limit from the result that has it; its limit in the other one counts as 0.
    """
    info = ["name", "score_bucket", "exposure", "current_limit"]
    cols = ["code", "proposed_limit", "over_new", "reason_code"]
    m = base[["code"] + info + cols[1:]].merge(
        scenario[["code"] + info + cols[1:]], on="code", how="outer", suffixes=("_base", "_scenario"))
    for c in info:
        m[c] = m[c + "_base"].where(m[c + "_base"].notna(), m[c + "_scenario"])
    m = m.drop(columns=[c + sfx for c in info for sfx in ("_base", "_scenario")])
    for c in ("proposed_limit_base", "proposed_limit_scenario"):
        m[c] = m[c].fillna(0.0)
    for c in ("over_new_base", "over_new_scenario"):
        m[c] = m[c].map(lambda x: bool(x) if isinstance(x, (bool, np.bool_)) else False).astype(bool)
    m["delta"] = m["proposed_limit_scenario"] - m["proposed_limit_base"]
    lim = m["delta"].abs() >= 0.5
    over = m["over_new_base"] != m["over_new_scenario"]
    m["change"] = np.select([lim & over, lim, over], ["BOTH", "LIMIT", "OVER_STATUS"], "")
    m = m[(m["change"] != "").to_numpy(bool)].copy()
    order = ["code"] + info + ["proposed_limit_base", "over_new_base", "reason_code_base",
                               "proposed_limit_scenario", "over_new_scenario", "reason_code_scenario",
                               "delta", "change"]
    m = m[order]
    m["_abs"] = m["delta"].abs()
    return m.sort_values(["_abs", "code"], ascending=[False, True]).drop(columns="_abs").reset_index(drop=True)


def data_summary(data: LoadedData, params: Params | None = None) -> dict[str, Any]:
    """Numbers for the Data page: rows read, active customers, intercompany, Cerved matches."""
    p = params or Params()
    out: dict[str, Any] = {"rows_read": dict(data.rows_read), "sources": dict(data.sources),
                           "missing": data.missing, "reference_date": reference_date(data, p),
                           "default_reference_date": data.default_reference_date}
    if data.ar is not None:
        out["ar_rows_clean"] = len(data.ar)
        out["ar_customers"] = int(data.ar["customer"].nunique())
    if data.cerved is not None:
        out["cerved_rows"] = len(data.cerved)
    c = data.matched_customers(p.cerved_reject_vat_conflict)
    if c is None:
        return out
    active = (c["balance"] != 0) | (c["turnover_12m"] > 0)
    ic = c["code"].isin(set(p.intercompany_codes))
    sim = active & ~ic
    out.update({
        "n_customers": len(c), "n_active_all": int(active.sum()),
        "n_intercompany_excluded": int((active & ic).sum()), "n_active": int(sim.sum()),
        "match_code_n": int((sim & c["match_method"].eq("code")).sum()),
        "match_vat_n": int((sim & c["match_method"].eq("vat")).sum()),
        "match_none_n": int((sim & c["match_method"].isna()).sum()),
        "vat_conflict_n": int((sim & c["vat_conflict"]).sum()),
    })
    return out
