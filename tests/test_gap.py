"""Purchase gaps on the Customer page: months without invoices that lower the 12-month average.

Explanation only: the proposed limit must not change. Real case: ACTIV METAL GAZ (30002232), no
purchases from December 2025 to April 2026 (first invoice 27/05/2026), then about 45,000 RON a month;
with the proposed 53,000 orders would have been held in 5 months, with today's 90,000 never.
"""
from __future__ import annotations

import pandas as pd

from core import engine, texts as TX
from core.params import Params
from tests.test_app import core_data


def _sim():
    d = core_data()
    return d, engine.simulate(d, Params(), include_all=True), engine.reference_date(d, Params())


def test_purchase_months_are_calendar_months():
    d, r, ref = _sim()
    pm = engine.purchase_months(d.ar, "30002232", ref)
    assert len(pm) == 12 and pm["month"].iloc[0] == pd.Timestamp("2025-12-01")
    assert pm["month"].iloc[-1] == pd.Timestamp("2026-11-01") and pm["end"].iloc[-1] == ref.normalize()
    assert pm["partial"].tolist() == [False] * 11 + [True]
    assert pm["end"].iloc[1] == pd.Timestamp("2026-01-31")
    assert pm["amount"].iloc[:5].eq(0).all() and pm["amount"].iloc[5:].gt(0).all()   # first purchase 27/05
    a = d.ar[(d.ar["customer"] == "30002232") & (d.ar["amount"] > 0)]
    a = a[(a["invoice_date"] >= "2025-12-01") & (a["invoice_date"] <= ref)]
    assert abs(pm["amount"].sum() - a["amount"].sum()) < 0.01


def test_peak_open_counts_items_across_months():
    d, r, ref = _sim()
    pm = engine.purchase_months(d.ar, "30002232", ref).set_index("month")
    # October: the 15/10 invoices (31,000) are still open when the 27/10 one (45,450) arrives,
    # together with the September ones paid on 29/10
    assert abs(pm.loc["2026-10-01", "peak_open"] - 87_639.44) < 0.01
    # July: June's invoices are still open at the start of July (no July invoice raises the peak)
    assert pm.loc["2026-07-01", "peak_open"] > pm.loc["2026-07-01", "amount"]
    assert engine.blocked_months(pm.reset_index(), 53_000) == [False] * 6 + [True, True, True, False, True, True]
    assert not any(engine.blocked_months(pm.reset_index(), 90_000))


def test_gap_effect_activ_metal_gaz_and_formula_unchanged():
    d, r, ref = _sim()
    row = r[r["code"] == "30002232"].iloc[0]
    g = engine.purchase_gap_effect(row, engine.purchase_months(d.ar, "30002232", ref))
    assert (g["bought"], g["empty"]) == (7, 5)
    assert abs(g["monthly_12"] - row["turnover_12m"] / 12) < 0.01
    assert abs(g["monthly_bought"] - row["turnover_12m"] / 7) < 0.01
    assert g["limit"] == row["proposed_limit"] == 53_000 and g["limit_alt"] == 91_000


def test_gap_effect_only_for_twelve_month_average():
    d, r, ref = _sim()
    young = r[r["age_band"].eq("YOUNG") & r["proposed_limit"].gt(0)].iloc[0]
    assert engine.purchase_gap_effect(young, engine.purchase_months(d.ar, young["code"], ref)) is None
    zero = r[r["proposed_limit"].eq(0) & r["turnover_12m"].gt(0)].iloc[0]
    assert engine.purchase_gap_effect(zero, engine.purchase_months(d.ar, zero["code"], ref)) is None
    full = pd.DataFrame({"month": [ref] * 12, "end": [ref] * 12, "amount": [1.0] * 12, "peak_open": [1.0] * 12, "peak_overdue": [0.0] * 12,
                         "partial": [False] * 12})
    row = r[r["code"] == "30002232"].iloc[0]
    assert engine.purchase_gap_effect(row, full) is None          # bought every month: no note


def test_customer_page_shows_gap_note_and_chart():
    from tests.test_app import go, new_app, watch
    with watch():
        for lang in ("EN", "IT"):
            lg = lang.lower()
            at = go(new_app(lang), "customer")
            at.session_state["customer"] = "30002232"
            go(at, "customer")
            warn = " ".join(w.value for w in at.warning)
            assert "5" in warn and TX.T("gap_note_tail", lg) in warn, warn
            assert any(TX.T("gap_chart_title", lg) in m.value for m in at.markdown)
            md = " ".join(m.value for m in at.markdown)
            assert "5" in md and TX.T("blk_sum_cur_no", lg, v=TX.fmt_amount(90000, lg) + " RON") in md, md[-600:]
            m = {x.label: x.value for x in at.metric}
            assert m[TX.T("cust_t_new", lg)].startswith("53")       # the proposed limit does not change


def test_overdue_line_punctual_vs_late_payer():
    """PHINIA DELPHI (71779810) pays at 90 days on time: exposure grows with purchases, overdue stays 0
    beyond the 5-day tolerance (a few invoices paid 1-2 days late). SPOT SERV (30006222) pays late."""
    d, r, ref = _sim()
    ph = engine.purchase_months(d.ar, "71779810", ref, overdue_grace_days=5)
    assert ph["peak_open"].iloc[-1] > 270_000 and ph["peak_overdue"].eq(0).all()
    raw = engine.purchase_months(d.ar, "71779810", ref)            # no tolerance: September shows up
    assert raw["peak_overdue"].iloc[9] > 40_000
    sp = engine.purchase_months(d.ar, "30006222", ref, overdue_grace_days=5)
    assert sp["peak_overdue"].iloc[-1] > 300_000
    assert (sp["peak_overdue"] <= sp["peak_open"] + 0.01).all()
