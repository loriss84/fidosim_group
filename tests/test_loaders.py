"""Recognition by columns, cleaning, Cerved matching and data-quality findings."""
import io

import pandas as pd

from core.loaders import LoaderError, detect_kind, load_files, normalize_vat, code_to_str
from tests.helpers import AR_DEFAULT, CF_DEFAULT, CV_DEFAULT, ar_row, cf_row, cv_row, make_data


def _xlsx(df: pd.DataFrame, sheet: str = "Sheet1") -> bytes:
    b = io.BytesIO()
    df.to_excel(b, sheet_name=sheet, index=False)
    return b.getvalue()


def test_detect_kind_and_helpers():
    assert detect_kind(CF_DEFAULT) == "checkfidi"
    assert detect_kind(CV_DEFAULT) == "cerved"
    assert detect_kind(AR_DEFAULT) == "ar124"          # headers with newlines
    assert detect_kind(["a", "b"]) is None
    assert normalize_vat("RO 14697790") == "14697790" and normalize_vat("ro-123") == "123"
    assert normalize_vat("BG 121093877  ") == "BG121093877" and normalize_vat("  ") is None
    assert code_to_str(30001539.0) == "30001539" and code_to_str(" 42 ") == "42"
    assert code_to_str("30001539.0") == "30001539" and code_to_str(None) is None


def test_load_bytes_detection_and_missing_files():
    cf = pd.DataFrame([cf_row(code="0123", t12=100, balance=None)])
    ar = pd.DataFrame([ar_row(123, "2026-06-01", "2026-07-01", 10, "2026-07-01"),
                       ar_row("Total 123", "2026-06-01", "2026-07-01", 10)])
    junk = pd.DataFrame({"foo": [1]})
    d = load_files([("anything.xlsx", _xlsx(cf, "Result")), ("x.xlsx", _xlsx(ar)), ("j.xlsx", _xlsx(junk))])
    assert d.checkfidi is not None and d.ar is not None and d.cerved is None
    assert d.checkfidi.loc[0, "code"] == "123"                       # numeric code: leading zeros dropped
    assert d.checkfidi.loc[0, "balance"] == 0                        # NaN amount -> 0
    assert len(d.ar) == 1 and d.default_reference_date == pd.Timestamp("2026-06-01")
    codes = {f.code for f in d.findings}
    assert {"MISSING_CERVED", "FILE_INVALID", "AR_TOTAL_ROWS_DROPPED"} <= codes
    miss = next(f for f in d.findings if f.code == "MISSING_CERVED")
    assert "cerved_ceiling" in miss.details["unavailable"]
    assert d.ok


def test_missing_column_error():
    cf = pd.DataFrame([cf_row(code="1")]).drop(columns=["Credit Limit"])
    try:
        load_files([("cf.xlsx", _xlsx(cf))], strict=True)
    except LoaderError as e:
        assert "Credit Limit" in str(e)
    else:
        raise AssertionError("LoaderError expected")
    d = load_files([("cf.xlsx", _xlsx(cf))])
    f = next(f for f in d.findings if f.code == "FILE_INVALID")
    assert "Credit Limit" in f.details["message"] and not d.ok


def test_cerved_matching_rules():
    cf = [cf_row(code="1", vat="RO111", t12=1), cf_row(code="2", vat="RO222", t12=1),
          cf_row(code="3", vat="RO333", t12=1), cf_row(code="4", vat="RO444", t12=1),
          cf_row(code="5", vat=None, t12=1)]
    cv = [cv_row(code=1.0, vat="RO 999", name="WRONG CO"),       # duplicated code 1, other VAT
          cv_row(code=1.0, vat="RO 111", name="RIGHT CO"),       # same VAT -> preferred
          cv_row(code=2.0, vat="RO 777", name="A"),              # duplicated, no VAT equal -> first
          cv_row(code=2.0, vat="RO 778", name="B"),
          cv_row(code=None, vat="RO 333", name="BY VAT"),        # code 3 matched by VAT
          cv_row(code=99.0, vat="RO 444", name="FIRST VAT"),     # code 4 by VAT: first row
          cv_row(code=98.0, vat="RO444", name="SECOND VAT"),
          cv_row(code=50.0, vat="RO 5050", name="NOBODY")]
    d = make_data(cf, cv)
    c = d.customers.set_index("code")
    assert c.loc["1", "cv_name"] == "RIGHT CO" and c.loc["1", "match_method"] == "code"
    assert not c.loc["1", "vat_conflict"]
    # code 2: both Cerved rows have another VAT -> not used; no VAT fallback -> not in Cerved
    assert not c.loc["2", "in_cerved"] and bool(c.loc["2", "vat_conflict"])
    assert c.loc["2", "conflict_cv_name"] == "A" and not c["vat_differs"].any()
    assert c.loc["3", "cv_name"] == "BY VAT" and c.loc["3", "match_method"] == "vat"
    assert c.loc["4", "cv_name"] == "FIRST VAT"
    assert not c.loc["5", "in_cerved"]
    f = {x.code: x for x in d.findings}
    assert f["CV_DUP_CODE"].count == 2 and set(f["CV_DUP_CODE"].details["codes_with_different_vat"]) == {"1", "2"}
    assert "MATCH_VAT_DIFFERS" not in f and f["MATCH_VAT_CONFLICT"].count == 1
    assert f["MATCH_VAT_CONFLICT"].details["codes"] == ["2"] and f["CV_NO_CODE"].count == 1
    assert f["CV_UNMATCHED"].count == 5      # WRONG CO, A, B, SECOND VAT, NOBODY
    # legacy rule (parameter cerved_reject_vat_conflict=False): first row, flagged vat_differs
    leg = d.matched_customers(reject_vat_conflict=False).set_index("code")
    assert leg.loc["2", "cv_name"] == "A" and bool(leg.loc["2", "vat_differs"])
    assert leg.loc["1", "cv_name"] == "RIGHT CO"


def test_vat_conflict_falls_back_to_vat_and_missing_vat_keeps_code_match():
    cf = [cf_row(code="71782284", name="AMERICAN FC SRL", vat="RO52383839", t12=1),
          cf_row(code="2", vat="RO222", t12=1), cf_row(code="3", vat=None, t12=1),
          cf_row(code="4", vat="RO444", t12=1)]
    cv = [cv_row(code=71782284.0, vat="RO 16345847", name="AMERICAN FOOD CATERING SRL"),
          cv_row(code=2.0, vat="RO 999", name="OTHER"), cv_row(code=None, vat="RO222", name="TWO BY VAT"),
          cv_row(code=3.0, vat="RO 333", name="THREE"),          # Check fidi VAT blank: code match kept
          cv_row(code=4.0, vat=None, name="FOUR")]               # Cerved VAT blank: code match kept
    d = make_data(cf, cv)
    c = d.customers.set_index("code")
    assert not c.loc["71782284", "in_cerved"] and c.loc["71782284", "vat_conflict"]
    assert c.loc["2", "cv_name"] == "TWO BY VAT" and c.loc["2", "match_method"] == "vat" and c.loc["2", "vat_conflict"]
    assert c.loc["3", "cv_name"] == "THREE" and c.loc["4", "cv_name"] == "FOUR"
    f = next(x for x in d.findings if x.code == "MATCH_VAT_CONFLICT")
    assert f.count == 2 and "71782284 AMERICAN FC SRL" in f.examples[0]
    assert f.details["rematched_by_vat"] == 1 and f.details["not_in_cerved"] == 1
    from core.engine import simulate
    from core.params import Params
    r = simulate(d, Params(reference_date="2026-11-20")).set_index("code")
    assert r.loc["71782284", "score_bucket"] == "NONE" and r.loc["71782284", "vat_conflict"]
    r = simulate(d, Params(reference_date="2026-11-20", cerved_reject_vat_conflict=False)).set_index("code")
    assert r.loc["71782284", "in_cerved"] and r.loc["71782284", "vat_differs"]
