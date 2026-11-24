"""v3.2: customer-age bands (NEW / YOUNG / CONSOLIDATED / NO_HISTORY), the minimum number of invoices for
the bonus / malus, the customer master MD105 (account opening date) and the AR124 coverage check.

Synthetic customers, reference date 20/11/2026, contractual terms 30 days, Cerved "Affidabile" with no
suggested limit unless stated. Turnover 40.000 for a customer active 4 months: 10.000 a month,
M1 = 10.000 x 30/30 x 1,1 = 11.000, base 22.000, risk factor 1 -> 22.000 (the v3.1 rule: 40.000 / 12 ->
7.333 a month -> 16.133 -> 17.000).
"""
from __future__ import annotations

import io
import json
import math

import numpy as np
import openpyxl
import pandas as pd

from core import explain as X
from core import texts as T
from core.engine import (age_band, age_findings, ar_coverage_months, coverage_finding, months_active,
                         months_between, simulate)
from core.export import AGE_COLUMNS, to_excel
from core.kpi import age_breakdown, kpis
from core.loaders import LoadedData, clean_ar, clean_cerved, clean_checkfidi, clean_md105, load_files
from core.params import V31, Params
from core.sensitivity import sensitivity
from tests.helpers import AR_DEFAULT, CV_DEFAULT, REF, ar_row, cf_row, close, cv_row, one
from ui import logic as LG
from ui import scenarios as SC

P = Params(reference_date=REF)          # v3.2 default
REFT = pd.Timestamp(REF)
MD_HEADERS = ["Tipo Cliente", "Stato Cliente", "Cliente", "Descrizione Cliente", "Tax ID", "Payment Terms - A/R",
              "Date - Account Opened"]


def _inv(code: int, first: str, n_due: int = 3, amount: float = 1000.0, delay: int = 3) -> list[dict]:
    """``n_due`` invoices already due (terms 30, paid ``delay`` days after the due date: 3 = within the
    tolerance, no bonus / malus), the first one dated
    ``first`` (it may be outside the 12-month window: it only sets the age)."""
    out = [ar_row(code, first, pd.Timestamp(first) + pd.Timedelta(days=30), amount,
                  pd.Timestamp(first) + pd.Timedelta(days=30 + delay))]
    for i in range(n_due - 1):   # the others inside the window, all due by the reference date
        inv = pd.Timestamp("2026-09-01") + pd.Timedelta(days=i)
        out.append(ar_row(code, inv, inv + pd.Timedelta(days=30), amount, inv + pd.Timedelta(days=30 + delay)))
    return out


def _md(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame([{"Tipo Cliente": "C", "Stato Cliente": 0, "Cliente": c, "Descrizione Cliente": "X",
                          "Tax ID": None, "Payment Terms - A/R": "E30", "Date - Account Opened": pd.Timestamp(d)}
                         for c, d in rows], columns=MD_HEADERS)


def _data(cf: list[dict], ar: list[dict], cv: list[dict] | None = None, md: list[tuple] | None = None,
          anchor: bool = True) -> LoadedData:
    """``anchor``: add an invoice of another customer on 01/01/2024 so the AR124 file starts well before the
    test customers' first invoices (no left-censoring unless a test wants it)."""
    if anchor:
        ar = [ar_row(999999, "2024-01-01", "2024-01-31", 1.0, "2024-01-31")] + list(ar)
    ld = LoadedData()
    ld.checkfidi, _ = clean_checkfidi(pd.DataFrame(cf))
    ld.cerved, _ = clean_cerved(pd.DataFrame(cv or [cv_row(code=float(r["Code"])) for r in cf], columns=list(CV_DEFAULT)))
    ld.ar, _ = clean_ar(pd.DataFrame(ar, columns=list(AR_DEFAULT)))
    if md is not None:
        ld.md105, _ = clean_md105(_md(md))
    return ld.finalize()


def test_months_between_and_band_boundaries():
    assert months_between("2025-11-20", REF) == 12 and months_between("2026-08-20", REF) == 3
    close(months_between("2026-08-23", REF), 2 + 28 / 31)          # 2,9 months
    close(months_between("2025-11-23", REF), 11 + 28 / 31)         # 11,9 months
    assert months_between(REF, REF) == 0 and months_between("2027-01-01", REF) == 0
    assert math.isnan(months_between(None, REF))
    ages = np.array([2.9, 3.0, 11.9, 12.0, np.nan, 0.0, 40.0])
    assert list(age_band(ages, P)) == ["NEW", "YOUNG", "YOUNG", "CONSOLIDATED", "NO_HISTORY", "NEW", "CONSOLIDATED"]
    ma = months_active(ages, age_band(ages, P), P)
    assert np.allclose(ma, [2.9, 3.0, 11.9, 12, 12, 1.0, 12])     # at least 1, at most 12
    # a consolidated threshold above 12: young customers aged 12-18 still divide by 12 at most
    p18 = P.replace(consolidated_months=18)
    ma18 = months_active(np.array([15.0, 0.2]), age_band(np.array([15.0, 0.2]), p18), p18)
    assert list(ma18) == [12, 1]
    assert (months_active(ages, age_band(ages, P), P.replace(age_bands_enabled=False)) == 12).all()


def test_bands_on_invoices_and_annualisation_example():
    cf = [cf_row(code=str(i), t12=40_000) for i in range(1, 7)]
    ar = (_inv(1, "2026-08-23", delay=0) + _inv(2, "2026-08-20") + _inv(3, "2025-11-23") + _inv(4, "2025-11-20")
          + _inv(5, "2026-07-20"))                                   # 6: no invoice at all
    r = simulate(_data(cf, ar), P)
    bands = {c: one(r, c).age_band for c in "123456"}
    assert bands == {"1": "NEW", "2": "YOUNG", "3": "YOUNG", "4": "CONSOLIDATED", "5": "YOUNG", "6": "NO_HISTORY"}
    x = one(r, "5")             # the worked example: 40.000 over 4 months active -> 10.000 a month
    assert x.age_months == 4 and x.months_active == 4 and x.monthly_revenue_used == 10_000
    close(x.m1, 11_000)
    assert x.proposed_limit == 22_000 and x.reason_code == X.R_YOUNG_CUSTOMER
    assert one(r, "4").monthly_revenue_used == 40_000 / 12 and one(r, "4").proposed_limit == 8_000
    assert one(r, "6").months_active == 12 and one(r, "6").behaviour_pct == 0 and one(r, "6").proposed_limit == 8_000
    assert (r["months_active"] >= 1).all() and (r["months_active"] <= 12).all()
    n = one(r, "1")             # new: annualised, no bonus / malus (on time: v3.1 would give +5%), flag
    assert n.behaviour_band == "NEW_CUSTOMER" and n.behaviour_pct == 0 and n.revenue_check_flag
    assert n.reason_code == X.R_NEW_CUSTOMER and LG.flags(n, "en").endswith(T.T("flag_new_customer", "en"))
    # the explanation shows how the monthly revenue is obtained
    rows = LG.step_rows(x, P, "en")
    assert rows[1]["calc"] == "turnover 40,000 ÷ 4 months active (young customer)" and rows[1]["ron"] == "10,000"
    st = {s["step"]: s for s in X.steps(x, P)}
    assert st["S_AGE_YOUNG"]["amount"] == 10_000
    txt = {t["step"]: t["calc"] for t in X.steps_text(X.steps(x, P), "en")}
    assert "turnover 40,000 ÷ 4 months active" in txt["S_AGE_YOUNG"] and txt["S_M1"].startswith("40,000 / 4 × 30")
    assert LG.why_change(x, P, "en").startswith("Higher: customer active for 4 months, its turnover 40,000 RON counts "
                                                "over 4 months (10,000 RON a month); the formula gives 22,000 RON")
    assert "Confirm the revenue with the sales estimate" in LG.reason_long(n, P, "en")
    # bands off: the v3.1 rule (turnover / 12, bonus / malus for everyone with measured days)
    off = simulate(_data(cf, ar), P.replace(**V31))
    assert (off["months_active"] == 12).all() and one(off, "5").proposed_limit == 8_000
    assert one(off, "1").behaviour_band == "BONUS"
    k = kpis(r)
    assert (k["age_new_n"], k["age_young_n"], k["age_consolidated_n"], k["age_no_history_n"]) == (1, 3, 1, 1)
    ab = age_breakdown(r).set_index("age_band")
    assert ab.loc["YOUNG", "n"] == 3 and ab["limits_proposed"].sum() == r["proposed_limit"].sum()


def test_behaviour_min_invoices_gate():
    cf = [cf_row(code=str(i), t12=1_200_000) for i in (1, 2, 3)]
    ar = _inv(1, "2025-01-10", n_due=3, delay=0) + _inv(2, "2025-01-10", n_due=2, delay=0) + _inv(3, "2025-01-10", n_due=3, delay=60)
    d = _data(cf, ar)
    r = simulate(d, P)
    # invoice of 10/01/2025 is outside the window: customer 1 has 2 invoices due in the window
    assert one(r, "1").behaviour_invoices_n == 2 and one(r, "1").behaviour_band == "FEW_INVOICES"
    assert one(r, "1").behaviour_pct == 0 and one(r, "1").proposed_limit == 220_000
    for mn, exp in ((0, "BONUS"), (2, "BONUS"), (3, "FEW_INVOICES")):
        assert one(simulate(d, P.replace(behaviour_min_invoices=mn)), "1").behaviour_band == exp, mn
    r2 = simulate(d, P.replace(behaviour_min_invoices=2))
    assert one(r2, "1").proposed_limit == 231_000 and one(r2, "3").behaviour_band == "MALUS"
    assert one(r2, "3").proposed_limit == 198_000
    assert one(r, "3").proposed_limit == 220_000           # the gate removes the malus too
    # an open invoice not yet due does not count
    ar_open = _inv(4, "2025-01-10", n_due=1) + [ar_row(4, "2026-11-10", "2026-12-10", 1000.0)] * 3
    r4 = simulate(_data([cf_row(code="4", t12=1_200_000)], ar_open), P.replace(behaviour_min_invoices=1))
    assert one(r4, "4").behaviour_invoices_n == 0 and one(r4, "4").behaviour_band in ("FEW_INVOICES", "NONE")
    k = kpis(r)
    assert k["behaviour_few_n"] == 3 and k["behaviour_bonus_n"] == 0
    rows = LG.step_rows(one(r, "1"), P, "en")
    assert rows[6]["calc"] == "2 invoices already due, minimum 3 → no bonus, no malus"


def test_cerved_ceiling_minimum_and_special_classes_with_age():
    cf = [cf_row(code="1", t12=40_000), cf_row(code="2", t12=4_000), cf_row(code="3", t12=40_000, risk="S09"),
          cf_row(code="4", t12=0, balance=100), cf_row(code="5", t12=40_000)]
    cv = [cv_row(code=1.0, fido=15_000.7), cv_row(code=2.0), cv_row(code=3.0), cv_row(code=4.0),
          cv_row(code=5.0, score="CAUTELA")]
    ar = sum((_inv(i, "2026-07-20") for i in range(1, 6)), [])
    r = simulate(_data(cf, ar, cv), P)
    a = one(r, "1")       # annualised 22.000, Cerved 15.000,7 -> 15.000 (hard ceiling, whole RON)
    assert a.limit_after_coef == 22_000 and a.proposed_limit == 15_000 and a.reason_code == X.R_CERVED_CAP
    b = one(r, "2")       # 4.000 / 4 = 1.000 a month -> 2.200 -> 3.000 -> minimum 5.000
    assert b.monthly_revenue_used == 1_000 and b.proposed_limit == 5_000 and b.reason_code == X.R_MINIMUM
    assert one(r, "3").proposed_limit == 0 and one(r, "3").reason_code == X.R_SPECIAL
    assert one(r, "4").proposed_limit == 0 and one(r, "4").reason_code == X.R_NO_TURNOVER
    c = one(r, "5")       # caution 0,7 on the annualised revenue: 22.000 x 0,7 = 15.400 -> 16.000
    assert c.proposed_limit == 16_000 and c.reason_code == X.R_YOUNG_CUSTOMER
    assert "risk factor 0.70" in LG.reason_long(c, P, "en")


def test_md105_opening_date_earlier_invoice_and_missing_customer():
    cf = [cf_row(code=str(i), t12=40_000) for i in (1, 2, 3, 4)]
    ar = _inv(1, "2026-10-01") + _inv(2, "2026-01-05") + _inv(3, "2026-07-20") + _inv(4, "2026-09-01")
    md = [(1, "2015-03-01"),          # old account, occasional buyer: consolidated (AR124 alone says new)
          (2, "2026-07-20"),          # code re-created: first invoice 196 days before -> the invoice
          (4, "2026-09-15")]          # first invoice 14 days before the opening: within 31 days, MD105 kept
    d = _data(cf, ar, md=md)
    r = simulate(d, P)
    assert one(r, "1").age_band == "CONSOLIDATED" and one(r, "1").age_source == "md105"
    assert one(r, "1").proposed_limit == 8_000
    x = one(r, "2")
    assert x.age_source == "ar124_earlier" and x.age_start_date == pd.Timestamp("2026-01-05")
    close(x.age_months, months_between("2026-01-05", REF))
    assert one(r, "3").age_source == "ar124" and pd.isna(one(r, "3").opened_date) and one(r, "3").age_months == 4
    assert one(r, "4").age_source == "md105" and one(r, "4").age_start_date == pd.Timestamp("2026-09-15")
    f = {x.code: x for x in age_findings(r, d, P)}
    assert f["AGE_INVOICE_BEFORE_OPENING"].details["codes"] == ["2"]
    assert f["MD_CUSTOMER_MISSING"].details["codes"] == ["3"]
    assert coverage_finding(d, P) is None                 # MD105 loaded: no coverage warning
    # without MD105 the same invoices say "new" for customer 1
    r0 = simulate(_data(cf, ar), P)
    assert one(r0, "1").age_band == "NEW" and one(r0, "1").age_source == "ar124"
    # a customer in MD105 without invoices gets its band from the opening date (no bonus / malus anyway)
    r5 = simulate(_data([cf_row(code="9", t12=12_000)], [], md=[(9, "2026-07-20")]), P)
    assert one(r5, "9").age_band == "YOUNG" and one(r5, "9").months_active == 4 and one(r5, "9").behaviour_pct == 0
    # quality rows on the Data page, IT / EN
    for lang in ("it", "en"):
        keys = {c["key"]: c for c in LG.quality_checks(d, r, P, lang)}
        assert keys["dq_age_before_opening"]["count"] == 1 and len(keys["dq_age_before_opening"]["rows"]) == 1
        assert "dq_md_missing" in keys and "dq_ar_short_history" not in keys
        assert "{" not in keys["dq_age_before_opening"]["meaning"]


def test_md105_file_detected_with_title_row():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MD105.Customer Master"
    ws.append(["MD105 - Customer Master (report title)"])
    ws.append(MD_HEADERS)
    ws.append(["C", 0, 30001, "ALFA", "RO1", "E60", pd.Timestamp("2020-01-31").to_pydatetime()])
    ws.append(["C", 0, " 30002 ", "BETA", None, "E01", pd.Timestamp("2006-08-31").to_pydatetime()])
    ws.append(["C", 0, 30001.0, "ALFA bis", None, "E01", pd.Timestamp("2019-05-01").to_pydatetime()])
    b = io.BytesIO()
    wb.save(b)
    d = load_files([("anagrafica.xlsx", b.getvalue())], strict=True)
    assert d.sources == {"md105": "anagrafica.xlsx"} and d.rows_read["md105"] == 3
    assert "md105" not in d.missing and not d.ok          # optional file; Check fidi still needed
    m = d.md105.set_index("customer")
    assert list(m.index) == ["30001", "30002"] and m.loc["30001", "opened_date"] == pd.Timestamp("2019-05-01")
    assert {f.code for f in d.findings} >= {"MD_DUP_CODE"}


def test_coverage_finding_12_and_24_months():
    cf = [cf_row(code="1", t12=40_000)]
    ar12 = [ar_row(1, "2025-11-20", "2025-12-20", 10.0, "2025-12-20"), ar_row(1, REF, "2026-12-20", 10.0)]
    ar24 = [ar_row(1, "2024-11-20", "2024-12-20", 10.0, "2024-12-20"), ar_row(1, REF, "2026-12-20", 10.0)]
    d12, d24 = _data(cf, ar12, anchor=False), _data(cf, ar24, anchor=False)
    assert ar_coverage_months(d12.ar) == 12 and ar_coverage_months(d24.ar) == 24
    f = coverage_finding(d12, P)
    assert f.code == "AR_SHORT_HISTORY" and f.details == {"months": 12, "needed": 18}
    assert coverage_finding(d24, P) is None
    assert coverage_finding(d12, P.replace(age_bands_enabled=False)) is None     # only while banding is on
    assert coverage_finding(d12, P.replace(consolidated_months=6)) is None       # 12 >= 6 + 6
    assert coverage_finding(d24, P.replace(consolidated_months=24)) is not None  # 24 < 30
    # the banding is not switched off silently: the customer is still banded
    assert one(simulate(d12, P), "1").age_band == "CONSOLIDATED"
    for lang in ("it", "en"):
        keys = {c["key"]: c for c in LG.quality_checks(d12, simulate(d12, P), P, lang)}
        m = keys["dq_ar_short_history"]["meaning"]
        assert "12" in m and "18" in m and "MD105" in m and "{" not in m
        assert "{" not in T.t(T.DQ_TEXTS, "AR_SHORT_HISTORY", lang, **f.details)


def test_json_round_trip_excel_and_sensitivity():
    p = P.replace(age_bands_enabled=False, new_customer_months=2, consolidated_months=18, behaviour_min_invoices=5)
    assert Params.from_json(p.to_json()) == p
    old = {k: v for k, v in Params(multiplier=2.5).to_dict().items()
           if k not in ("age_bands_enabled", "new_customer_months", "consolidated_months", "behaviour_min_invoices")}
    name, loaded, ignored = SC.parse(json.dumps({"name": "v3.1 file", "params": old}).encode())
    assert not ignored and loaded.multiplier == 2.5 and loaded.age_bands_enabled
    assert (loaded.new_customer_months, loaded.consolidated_months, loaded.behaviour_min_invoices) == (3, 12, 3)
    assert Params(new_customer_months=13).validate()     # new above consolidated
    cf = [cf_row(code=str(i), t12=40_000) for i in (1, 2)]
    d = _data(cf, _inv(1, "2026-07-20") + _inv(2, "2024-01-01"), md=[(1, "2026-07-20"), (2, "2010-01-01")])
    r = simulate(d, P)
    for lang in ("it", "en"):
        li = 0 if lang == "it" else 1
        wb = openpyxl.load_workbook(io.BytesIO(to_excel(r, P, lang)))
        head = [c.value for c in wb.worksheets[0][1]]
        for c in AGE_COLUMNS:
            assert T.COLUMN_TEXTS[c][li] in head, c
        rows = {row[0].value: {h: c.value for h, c in zip(head, row)} for row in wb.worksheets[0].iter_rows(min_row=2)}
        x = rows["1"]
        assert x[T.COLUMN_TEXTS["age_band"][li]] == T.AGE_BAND_TEXTS["YOUNG"][lang]
        assert x[T.COLUMN_TEXTS["monthly_revenue_used"][li]] == 10_000
        assert x[T.COLUMN_TEXTS["months_active"][li]] == 4
        assert pd.Timestamp(x[T.COLUMN_TEXTS["opened_date"][li]]) == pd.Timestamp("2026-07-20")
        wb2 = openpyxl.load_workbook(io.BytesIO(to_excel(simulate(d, P.replace(**V31)), P.replace(**V31), lang)))
        assert T.COLUMN_TEXTS["age_band"][li] not in [c.value for c in wb2.worksheets[0][1]]
    for key, vals in (("new_customer_months", [0, 3, 6]), ("consolidated_months", [6, 12, 24]),
                      ("behaviour_min_invoices", [0, 3, 10])):
        s = sensitivity(d, P, key, vals, kpi_keys=["limits_proposed_active", "age_young_n"])
        assert list(s["value"]) == vals
    s = sensitivity(d, P, "consolidated_months", [3, 12], kpi_keys=["limits_proposed_active"])
    assert s["limits_proposed_active"].iloc[1] > s["limits_proposed_active"].iloc[0]


def test_rules_text_age():
    for lang in ("it", "en"):
        txt = LG.rules_text(LG.rules(P, 10, lang), lang)
        assert T.T("rl_div_age", lang) in txt and "MD105" in txt and "{" not in txt
        assert T.T("rl_beh_min", lang, n="3", months="12") in txt
        off = LG.rules_text(LG.rules(P.replace(**V31), 10, lang), lang)
        assert T.T("rl_age_off", lang).replace("**", "") in off and T.T("rl_beh_min_off", lang) in off
        assert "T12 / 12" in off


def test_left_censoring_first_invoice_at_file_start():
    """An age from the first AR124 invoice is only a minimum when that invoice is within 31 days of the start of
    the file: the customer may have bought before. Consolidated, shown as "at least N months"."""
    cf = [cf_row(code=str(i), t12=40_000) for i in (1, 2, 3, 4, 5)]
    start = [ar_row(99, "2026-01-01", "2026-01-31", 1.0, "2026-01-31")]           # the file starts 01/01/2026
    ar = (start + _inv(1, "2026-01-01") + _inv(2, "2026-01-30") + _inv(3, "2026-03-01") + _inv(4, "2026-02-05")
          + _inv(5, "2026-01-10"))
    # without MD105
    r = simulate(_data(cf, ar, anchor=False), P)
    x = one(r, "1")
    assert x.age_censored and x.age_band == "CONSOLIDATED" and x.months_active == 12 and x.proposed_limit == 8_000
    assert one(r, "2").age_censored and one(r, "2").age_band == "CONSOLIDATED"          # 29 days after the start
    assert not one(r, "4").age_censored and one(r, "4").age_band == "YOUNG"             # 35 days after the start
    y = one(r, "3")                                                                      # 2 months after the start
    assert not y.age_censored and y.age_band == "YOUNG" and y.months_active == y.age_months
    st = {t["step"]: t["calc"] for t in X.steps_text(X.steps(x, P), "en")}
    assert st["S_AGE_CENSORED"].startswith("First invoice 01/01/2026 at the start of the AR124 file (from 01/01/2026)")
    assert "age ≥" in st["S_AGE_CENSORED"] and "÷ 12" in st["S_AGE_CENSORED"]
    # with MD105: opening dates used; the re-created code (invoice > 31 days before the opening) at the file
    # start is censored too, one re-created 2 months after the start stays young; a customer missing in MD105
    # with its first invoice at the start is censored
    md = [(1, "2026-10-01"), (3, "2026-09-01"), (4, "2026-02-10")]
    r2 = simulate(_data(cf, ar, md=md, anchor=False), P)
    a = one(r2, "1")
    assert a.age_source == "ar124_earlier" and a.age_censored and a.age_band == "CONSOLIDATED"
    b = one(r2, "3")
    assert b.age_source == "ar124_earlier" and not b.age_censored and b.age_band == "YOUNG"
    c = one(r2, "4")                       # opening 5 days after the first invoice: MD105 date, not censored
    assert c.age_source == "md105" and not c.age_censored and c.age_band == "YOUNG"
    m = one(r2, "5")
    assert m.age_source == "ar124" and m.age_censored and m.age_band == "CONSOLIDATED"
    assert one(simulate(_data(cf, ar, md=md, anchor=False), P.replace(**V31)), "1").months_active == 12
    for lang in ("it", "en"):   # Customer page: "at least N months"
        assert T.T("pd_age_min", lang, months="10").startswith("≥ 10")
