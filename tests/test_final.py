"""Final review fixes (20/11/2026): explanation sentences always true, one term per concept, KPI split
of the customers over limit, approval materiality, Cerved values in whole RON everywhere, Julian /
out-of-range numeric dates, ambiguous separators, legacy terms on all rows, findings consistent with
the matching rule, integer parameters, Excel formats."""
import io
import re

import numpy as np
import openpyxl
import pandas as pd

from core import explain as X
from core import texts as T
from core.engine import payment_days, simulate
from core.export import to_excel
from core.kpi import kpis
from core.loaders import load_files, parse_dates, parse_numbers, parse_numbers_ex
from core.params import Params, OLD_V3
from tests.helpers import AR_DEFAULT, REF, ar_row, cf_row, cv_row, make_data, one
from ui import logic as LG

P = Params(reference_date=REF, **OLD_V3)  # unit tests of the v3 mechanics (v3.1: see test_behaviour)


def _xlsx(df: pd.DataFrame, sheet: str = "Sheet1") -> bytes:
    b = io.BytesIO()
    df.to_excel(b, sheet_name=sheet, index=False)
    return b.getvalue()


def _sentences(r: pd.DataFrame, p: Params, lang: str) -> list[tuple[str, str, str]]:
    out = []
    for _, row in r.iterrows():
        v = X.text_values(row, p)
        out.append((row["code"], T.t(T.REASON_LONG_TEXTS, row["reason_code"], lang, **v),
                    T.t(T.CHANGE_TEXTS, row["change_code"], lang, **v)))
    return out


def test_why_change_true_when_cerved_or_minimum_decides():
    """Review A: Cerved-capped customers whose formula is below Cerved, Silcotub-type cap, minimum."""
    cf = [cf_row(code="1", t12=1200, limit=1000),          # formula 154 -> min 5.000 -> Cerved 3.433
          cf_row(code="2", t12=60_000_000, limit=1000000),  # formula 11 M, Cerved 5.041.500
          cf_row(code="3", t12=24688, limit=10000),         # formula 4.526 -> 5.000 -> Cerved 4.582
          cf_row(code="4", t12=1200000, limit=500000),      # formula 220.000 -> Cerved 26.790
          cf_row(code="5", t12=12000, limit=100000),        # formula 2.200 -> minimum, lower
          cf_row(code="6", t12=12000, limit=1000),          # minimum, higher
          cf_row(code="7", t12=120000, limit=0)]            # new limit
    cv = [cv_row(code=1.0, fido=3433.4, score="CAUTELA"), cv_row(code=2.0, fido=5041500),
          cv_row(code=3.0, fido=4582.72), cv_row(code=4.0, fido=26790.53, score="CAUTELA"),
          cv_row(code=5.0), cv_row(code=6.0), cv_row(code=7.0)]
    r = simulate(make_data(cf, cv), P)
    codes = {c: one(r, c).change_code for c in "1234567"}
    assert codes == {"1": X.C_HIGHER_MINIMUM_CAPPED, "2": X.C_HIGHER_CERVED_CAP, "3": X.C_LOWER_ROUNDED_CAPPED,
                     "4": X.C_LOWER_CERVED_CAP, "5": X.C_LOWER_MINIMUM, "6": X.C_HIGHER_MINIMUM,
                     "7": X.C_HIGHER_NO_CURRENT}, codes
    for lang in ("it", "en"):
        for code, long_, why in _sentences(r, P, lang):
            assert "real" not in why and "reale" not in why and "{" not in long_ + why, (code, why)
            assert "bisogno reale" not in long_ and "would give more" not in long_
        en = {c: (lng, w) for c, lng, w in _sentences(r, P, "en")}
    assert "3,433 RON" in en["1"][1] and "154 RON" in en["1"][1] and "minimum" in en["1"][1]
    assert "held at the Cerved suggested limit (5,041,500 RON)" in en["2"][1]
    assert "4,582 RON" in en["3"][1] and "4,526 RON" in en["3"][1]
    assert "26,790 RON" in en["4"][1] and "26,791" not in en["4"][0] + en["4"][1]
    assert en["5"][1].startswith("Lower: the formula gives 2,200 RON, below the minimum")
    assert "not even with rounding or the 5,000 RON minimum" in en["1"][0]   # true for every capped one


def test_one_term_per_concept():
    """'multiplier' only for ×2, 'risk factor' / 'coefficiente di rischio' for the score coefficient,
    'Need (M1)' only for M1, never 'real need'."""
    tables = [T.REASON_TEXTS, T.REASON_LONG_TEXTS, T.CHANGE_TEXTS]
    for tb in tables:
        for code, e in tb.items():
            assert "multiplier" not in e["en"].lower() or "×{mult:x} multiplier" in e["en"], (code, e["en"])
            assert "moltiplicatore di rischio" not in e["it"].lower(), code
            assert "risk multiplier" not in e["en"].lower(), code
            assert "real need" not in e["en"].lower() and "bisogno reale" not in e["it"].lower(), code
            rest = re.sub(r"Need \(M1\)|orders need", "", e["en"]).lower()
            assert "need" not in rest, (code, e["en"])
    for k, e in T.TEXTS.items():
        assert "risk multiplier" not in e["en"].lower() and "moltiplicatore di rischio" not in e["it"].lower(), k
        assert "real need" not in e["en"].lower() and "bisogno reale" not in e["it"].lower(), k
    assert T.T("g_coef_t", "en") == "Risk factor" and T.T("g_coef_t", "it") == "Coefficiente di rischio"
    assert T.T("st_4", "en") == "Need (M1)" and T.T("st_4", "it") == "Bisogno (M1)"
    # IT / EN pairs carry the same placeholders
    for tb in tables + [T.STEP_TEXTS]:
        for code, e in tb.items():
            ph = lambda x: sorted(re.findall(r"\{(\w+)", str(x)))  # noqa: E731
            assert ph(e["it"]) == ph(e["en"]), code
    for k, e in T.TEXTS.items():
        assert sorted(re.findall(r"\{(\w+)", e["it"])) == sorted(re.findall(r"\{(\w+)", e["en"])), k


def test_real_data_sentences_and_kpi_split():
    from tests.test_app import core_data
    r = simulate(core_data(), Params(**OLD_V3))
    k = kpis(r)
    assert (k["over_new_n"], k["over_new_positive_n"], k["over_new_zero_n"]) == (290, 130, 160)
    assert (k["over_current_n"], k["over_current_positive_n"], k["over_current_zero_n"]) == (267, 202, 65)
    assert round(k["limits_proposed_scope"] / 1e6, 2) == 33.16 and round(k["limits_current_scope"] / 1e6, 2) == 32.10
    assert k["approval_n"] == 421 and (k["approval_tier1_n"], k["approval_tier2_n"], k["approval_tier3_n"]) == (401, 19, 1)
    # no sentence contradicts itself: "Higher" / "Lower" agree with the numbers quoted
    for lang in ("it", "en"):
        for code, long_, why in _sentences(r, Params(**OLD_V3), lang):
            assert "{" not in long_ + why and " - RON" not in why, (code, why)
    rr = r.set_index("code")
    for c in ("30018483", "30006372"):    # Multimedica, Concept-Grup: formula below current, Cerved held
        assert rr.loc[c, "change_code"] == X.C_HIGHER_MINIMUM_CAPPED
    assert rr.loc["30001539", "change_code"] == X.C_HIGHER_CERVED_CAP     # Silcotub


def test_reason_uses_whole_ron_ceiling():
    """explain: a Cerved value of 0,40 RON is "Cerved suggests 0" (whole RON), in any mode."""
    cf = [cf_row(code="1", t12=12000, balance=1), cf_row(code="2", t12=1200000, balance=1)]
    cv = [cv_row(code=1.0, fido=0.4), cv_row(code=2.0, fido=4999.9999999)]
    for kw in ({}, {"rounding_step": 500, "min_limit": 3000, "rounding_mode": "down"}):
        r = simulate(make_data(cf, cv), P.replace(**kw))
        assert one(r, "1").proposed_limit == 0 and one(r, "1").reason_code == X.R_CERVED_ZERO, kw
        # ceiling rounded to 6 decimals before truncation: 4.999,9999999 -> 5.000
        assert one(r, "2").ceiling_unit == 5000 and one(r, "2").proposed_limit == 5000
        assert one(r, "2").reason_code == X.R_CERVED_CAP
    v = X.text_values(one(r, "1"), P)
    assert v["cerved_limit"] == 0


def test_integer_parameters():
    assert Params().min_limit == 5000 and isinstance(Params().min_limit, int)
    assert Params(min_limit=5000.0).min_limit == 5000 and isinstance(Params(min_limit=5000.0).min_limit, int)
    assert Params(min_limit=5000.5).validate() and Params(rounding_step=500.5).validate()
    assert Params.from_dict({"min_limit": 5000.5}).min_limit == 5000      # JSON import: whole RON
    assert not Params(approval_min_change=0).validate()


def test_julian_and_out_of_range_numeric_dates():
    v, bad = parse_dates(pd.Series([126001, 125365, 124366, np.nan]))
    assert [str(x.date()) for x in v[:3]] == ["2026-01-01", "2025-12-31", "2024-12-31"] and not bad.any()
    v, bad = parse_dates(pd.Series([46000, 200000, 1e9, 106750]))      # Excel serial + out of range
    assert str(v[0].date()) == "2025-12-09" and v[1:].isna().all() and bad.tolist() == [False, True, True, True]
    # a whole AR124 column in JDE Julian format, and one with huge numbers: never FILE_INVALID
    cf = pd.DataFrame([cf_row(code="1", t12=120000, balance=1)])
    for inv, due, closed, julian in ((126001, 126031, 126020, True), (106750, 999999, 5e6, False)):
        ar = pd.DataFrame([ar_row(1, "2026-01-01", "2026-01-31", 1000.0)], columns=list(AR_DEFAULT))
        ar["Invoice Date"], ar["Due Date"], ar["Date Invoice Closed"] = [inv], [due], [closed]
        d = load_files([("cf.xlsx", _xlsx(cf, "Result")), ("ar.xlsx", _xlsx(ar))])
        codes = {f.code for f in d.findings}
        assert "FILE_INVALID" not in codes and d.ar is not None, codes
        if julian:
            assert str(d.ar["invoice_date"].iloc[0].date()) == "2026-01-01" and "BAD_DATES" not in codes
            assert payment_days(d.ar, pd.Timestamp(REF), 12).loc["1", "days_measured"] == 19
        else:
            assert "BAD_DATES" in codes and d.ar["invoice_date"].isna().all()


def test_ambiguous_separators_read_as_thousands_in_amounts():
    v, bad, amb = parse_numbers_ex(pd.Series(["12.500", "120,000", "7"]), amounts=True)
    assert v.tolist() == [12500.0, 120000.0, 7.0] and amb.tolist() == [True, True, False]
    assert parse_numbers(pd.Series(["12.500", "12.5"]), amounts=True)[0].tolist() == [12.5, 12.5]  # evidence
    assert parse_numbers(pd.Series(["12.500"]))[0].tolist() == [12.5]                             # not amounts
    d = make_data([cf_row(code="1", balance="12.500", t12="120.000", limit="3.000")])
    c = d.checkfidi.iloc[0]
    assert (c["balance"], c["turnover_12m"], c["credit_limit"]) == (12500, 120000, 3000)
    f = next(f for f in d.findings if f.code == "AMBIGUOUS_NUMBERS")
    assert f.count == 3 and f.severity == "warning" and f.details["kind"] == "checkfidi"
    assert T.t(T.DQ_TEXTS, "AMBIGUOUS_NUMBERS", "en", count=3, kind="checkfidi")


def test_legacy_terms_use_every_row():
    ar = [ar_row(1, "2026-01-01", "2026-03-31", 100, "2026-05-01"),
          ar_row(1, "2026-02-01", "2026-02-11", 100, "2026-02-21"),
          ar_row(1, "2026-02-15", "2026-02-20", 300, "2026-11-01"),
          ar_row(1, "2026-04-01", "2026-04-30", 1000),          # after the reference date
          ar_row(2, "2026-01-10", "2026-03-11", -100), ar_row(2, "2026-05-10", "2026-05-20", 100)]
    d = make_data([cf_row(code="1", t12=1), cf_row(code="2", t12=1)], None, ar)
    ref = pd.Timestamp("2026-03-01")
    new = payment_days(d.ar, ref, 12, terms_positive_only=True)
    old = payment_days(d.ar, ref, 12, terms_positive_only=False)
    assert new.loc["1", "days_terms"] == 10 and old.loc["1", "days_terms"] == 19.5    # 89, 10, 5, 29
    assert old.loc["2", "days_terms"] == 35                                            # 60 and 10


def test_findings_follow_the_matching_rule():
    cf = [cf_row(code="1", t12=1200000, balance=1, vat="RO111")]
    cv = [cv_row(code=1.0, vat="RO 999", fido=1000)]
    d = make_data(cf, cv)
    new = {f.code for f in d.findings_for(True)}
    old = {f.code for f in d.findings_for(False)}
    assert "MATCH_VAT_CONFLICT" in new and "MATCH_VAT_DIFFERS" not in new
    assert "MATCH_VAT_DIFFERS" in old and "MATCH_VAT_CONFLICT" not in old
    q = LG.quality_checks(d, simulate(d, P.replace(cerved_reject_vat_conflict=False)),
                          P.replace(cerved_reject_vat_conflict=False), "en")
    row = next(c for c in q if c["key"] == "dq_vat_mismatch")
    assert row["rows"] is not None and len(row["rows"]) == 1


def test_excel_whole_ron_match_labels_and_percent_kpis():
    cf = [cf_row(code="1", t12=1200000, balance=1, vat="RO1"), cf_row(code="2", t12=1200000, balance=1)]
    cv = [cv_row(code=1.0, vat="RO1", fido=26790.53, score="CAUTELA")]
    r = simulate(make_data(cf, cv), P)
    for lang, match in (("it", "codice"), ("en", "code")):
        wb = openpyxl.load_workbook(io.BytesIO(to_excel(r, P, lang)))
        ws = wb.worksheets[0]
        head = [c.value for c in ws[1]]
        row = {h: c.value for h, c in zip(head, ws[2])}
        lim = T.COLUMN_TEXTS["cerved_limit_ron"][0 if lang == "it" else 1]
        ceil = T.COLUMN_TEXTS["ceiling"][0 if lang == "it" else 1]
        assert row[lim] == 26790 and row[ceil] == 26790 and row[T.COLUMN_TEXTS["proposed_limit"][0 if lang == "it" else 1]] == 26790
        assert row[T.COLUMN_TEXTS["match_method"][0 if lang == "it" else 1]] == match
        row2 = {h: c.value for h, c in zip(head, ws[3])}
        assert row2[T.COLUMN_TEXTS["match_method"][0 if lang == "it" else 1]] == T.MATCH_TEXTS["none"][lang]
        kp = wb.worksheets[1]
        cells = {r_[1].value: r_[2] for r_ in kp.iter_rows(min_row=2)}
        assert cells["in_cerved_exposure_share_active"].number_format == "0.0%"
        assert cells["over_new_n"].number_format == "#,##0"


def test_customer_page_logic_bits():
    """Step 7 shows the whole-RON ceiling; late-payer note; exempt reason wording."""
    cf = [cf_row(code="1", t12=1200000, limit=381000), cf_row(code="2", t12=1200000, risk="EKM")]
    cv = [cv_row(code=1.0, fido=26790.53, score="CAUTELA")]
    r = simulate(make_data(cf, cv), P)
    rows = LG.step_rows(one(r, "1"), P, "en")
    assert rows[6]["ron"] == "26,790" and "26,790" in rows[6]["calc"]
    assert "Exempt class EKM, not rated by Cerved: monitoring limit" in LG.reason_long(one(r, "2"), P, "en")
    assert T.T("w_suffix_late", "en", meas="119", days="75", over="15") == \
        "Measured payment days 119; the formula counts at most 75 (terms + 15)."
