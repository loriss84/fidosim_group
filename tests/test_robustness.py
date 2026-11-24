"""Validator defects (20/11/2026): empty files, text amounts and dates, several companies,
optional columns, look-ahead with a past reference date, scenario comparison with customers
in one scenario only, parameter list normalisation, percent format in Excel, customer codes."""
import io
import math

import openpyxl
import pandas as pd

from core.engine import customer_invoices, payment_days, simulate
from core.export import to_excel
from core.kpi import changed_customers
from core.loaders import code_to_str, load_files, parse_dates, parse_numbers
from core.params import Params, OLD_V3
from tests.helpers import AR_DEFAULT, CF_DEFAULT, CV_DEFAULT, REF, ar_row, cf_row, cv_row, make_data, one

P = Params(reference_date=REF, **OLD_V3)  # unit tests of the v3 mechanics (v3.1: see test_behaviour)


def _xlsx(df: pd.DataFrame, sheet: str = "Sheet1") -> bytes:
    b = io.BytesIO()
    df.to_excel(b, sheet_name=sheet, index=False)
    return b.getvalue()


def _codes(d) -> dict:
    return {f.code: f for f in d.findings}


def test_ar124_headers_only_is_accepted():
    cf = pd.DataFrame([cf_row(code="1", t12=120000, balance=10)])
    ar = pd.DataFrame(columns=list(AR_DEFAULT))
    d = load_files([("cf.xlsx", _xlsx(cf, "Result")), ("ar.xlsx", _xlsx(ar))], strict=True)
    assert d.ar is not None and d.ar.empty and "ar124" not in d.missing
    f = _codes(d)
    assert "FILE_INVALID" not in f and f["FILE_EMPTY"].details["kind"] == "ar124"
    r = simulate(d, P)
    assert one(r, "1").days_source == "fallback" and one(r, "1").days_used == 30
    # empty Cerved too
    cv = pd.DataFrame(columns=list(CV_DEFAULT))
    d = load_files([("cf.xlsx", _xlsx(cf, "Result")), ("cv.xlsx", _xlsx(cv))], strict=True)
    assert d.cerved is not None and not d.customers["in_cerved"].any()


def test_text_amounts_parsed_and_failures_reported():
    v, bad = parse_numbers(pd.Series(["12.500,00", "12,500.00", " 1 200 ", "-3,5", "− 7", "(50)",
                                      "1.200.000,50", None, "", "abc", 4.0], dtype=object))
    assert v.tolist()[:7] == [12500.0, 12500.0, 1200.0, -3.5, -7.0, -50.0, 1200000.5]
    assert math.isnan(v[7]) and math.isnan(v[8]) and math.isnan(v[9]) and v[10] == 4.0
    assert bad.tolist() == [False] * 9 + [True, False]
    assert parse_numbers(pd.Series(["1,5", "2,25"]))[0].tolist() == [1.5, 2.25]          # decimal comma
    assert parse_numbers(pd.Series(["1,234,567", "12"]))[0].tolist() == [1234567.0, 12.0]  # thousands
    cf = [cf_row(code="1", balance="12.500,00", t12="1.200.000,50", limit="n/a"),
          cf_row(code="2", balance="oops", t12="120000")]
    d = make_data(cf)
    c = d.checkfidi.set_index("code")
    assert c.loc["1", "balance"] == 12500 and c.loc["1", "turnover_12m"] == 1200000.5
    f = _codes(d)["BAD_NUMBERS"]
    assert f.count == 2 and f.details["columns"] == {"Balance": 1, "Credit Limit": 1}
    assert any("oops" in e for e in f.examples)


def test_text_dates_day_first_and_failures_reported():
    v, bad = parse_dates(pd.Series(["03/02/2026", "03.02.2026", "2026-02-03", "3/2/26", "31/12/2026 10:30",
                                    "32/01/2026", None, ""], dtype=object))
    assert v[:4].tolist() == [pd.Timestamp("2026-02-03")] * 4
    assert v[4] == pd.Timestamp("2026-12-31 10:30")
    assert pd.isna(v[5]) and bad.tolist() == [False] * 5 + [True, False, False]
    real = pd.Series(pd.to_datetime(["2026-02-03", None]))
    assert parse_dates(real)[0].equals(real.astype("datetime64[ns]"))       # Excel dates unchanged
    rows = pd.DataFrame([ar_row(1, "2026-01-01", "2026-01-31", 100, "2026-02-10")] * 2, columns=list(AR_DEFAULT))
    rows["Invoice Date"] = ["03/02/2026", "not a date"]
    rows["Due Date"] = ["05/03/2026", "05/03/2026"]
    rows["Date Invoice Closed"] = ["01/04/2026", None]
    d = load_files([("cf.xlsx", _xlsx(pd.DataFrame([cf_row(code="1", t12=1)]), "Result")),
                    ("ar.xlsx", _xlsx(rows))])
    assert d.ar.loc[0, "invoice_date"] == pd.Timestamp("2026-02-03")
    assert d.ar.loc[0, "closed_date"] == pd.Timestamp("2026-04-01")
    f = _codes(d)
    assert f["BAD_DATES"].count == 1 and f["BAD_DATES"].details["columns"] == {"Invoice Date": 1}
    assert f["AR_NO_INVOICE_DATE"].count == 1


def test_several_companies_keep_most_frequent_with_finding():
    cf = [cf_row(code="50", t12=120000, balance=1, **{"Company Code": 42}),
          cf_row(code="51", t12=120000, balance=1, **{"Company Code": 42}),
          cf_row(code="50", t12=999999, balance=1, **{"Company Code": 43, "Company": "SIAD Other"})]
    d = make_data(cf)
    f = _codes(d)
    assert f["CF_MULTI_COMPANY"].count == 1 and f["CF_MULTI_COMPANY"].details["kept"] == "42"
    assert f["CF_MULTI_COMPANY"].details["codes_examples"] == ["50"]
    assert "CF_DUP_CODE" not in f                       # not silently dropped as a duplicate
    assert one(simulate(d, P), "50").turnover_12m == 120000


def test_optional_columns_missing_disable_only_their_feature():
    cf = pd.DataFrame([cf_row(code="60", t12=120000, balance=1)]).drop(columns=["VAT"])
    cv = pd.DataFrame([cv_row(code=60.0, fido=1000)]).drop(
        columns=["VALUTA", "FATTURATO_NO_BIL", "CLASSE_AFFIDABILITA"])
    d = load_files([("cf.xlsx", _xlsx(cf, "Result")), ("cv.xlsx", _xlsx(cv))], strict=True)
    miss = [f for f in d.findings if f.code == "COLUMN_MISSING"]
    assert {f.details["kind"] for f in miss} == {"checkfidi", "cerved"}
    feats = {x for f in miss for x in f.details["unavailable"]}
    assert feats == {"vat_matching", "currency", "plausibility", "reliability_class"}
    assert _codes(d)["CV_NO_CURRENCY"].details["assumed"] == "RON"
    r = simulate(d, P)
    x = one(r, "60")
    assert x.in_cerved and x.ceiling == 1000 and x.proposed_limit == 1000
    assert math.isnan(x.plausibility_ratio) and not x.plausibility_flag
    # a required column is still an error
    bad = pd.DataFrame([cv_row(code=60.0)]).drop(columns=["VALORE_FIDO"])
    d = load_files([("cv.xlsx", _xlsx(bad))])
    assert any(f.code == "FILE_INVALID" and "VALORE_FIDO" in f.details["message"] for f in d.findings)


def test_past_reference_date_has_no_look_ahead():
    rows = [ar_row(1, "2026-01-01", "2026-01-31", 300, "2026-11-01"),   # closed after ref: open at ref
            ar_row(1, "2026-02-15", "2026-02-20", 100, "2026-02-25"),   # closed before ref: 10 days
            ar_row(1, "2026-04-01", "2026-05-01", 1000, "2026-04-05")]  # dated after ref: ignored
    d = make_data([cf_row(code="1", t12=1)], ar=rows)
    ref = pd.Timestamp("2026-03-01")
    pdays = payment_days(d.ar, ref, 12).loc["1"]
    assert pdays["n_invoices"] == 2 and pdays["days_measured"] == 59     # weighted median: 59 (300) / 10 (100)
    assert pdays["days_terms"] == (30 + 5) / 2                           # the April invoice is ignored
    inv = customer_invoices(d.ar, "1", ref, 12)
    assert inv["days"].tolist() == [59, 10] and inv["is_open"].tolist() == [True, False]
    r = simulate(d, Params(reference_date="2026-03-01", cap_days_enabled=False, **OLD_V3))
    assert one(r, "1").days_measured == 59


def test_terms_from_positive_invoices_only():
    rows = [ar_row(1, "2026-06-01", "2026-07-01", 100, "2026-07-01"),     # 30
            ar_row(1, "2026-06-01", "2026-06-01", -50, "2026-06-01"),     # credit note: 0
            ar_row(1, "2026-06-01", "2026-06-01", -50, "2026-06-01"),     # credit note: 0
            ar_row(2, "2026-06-01", "2026-06-01", -50, "2026-06-01")]     # credit notes only
    d = make_data([cf_row(code="1", t12=1), cf_row(code="2", t12=1)], ar=rows)
    pdays = payment_days(d.ar, pd.Timestamp(REF), 12)
    assert pdays.loc["1", "days_terms"] == 30 and math.isnan(pdays["days_terms"].get("2", math.nan))
    legacy = payment_days(d.ar, pd.Timestamp(REF), 12, terms_positive_only=False)
    assert legacy.loc["1", "days_terms"] == 0 and legacy.loc["2", "days_terms"] == 0
    r = simulate(d, P)
    assert one(r, "2").days_source == "fallback"
    assert one(simulate(d, P.replace(terms_positive_only=False)), "2").days_source == "terms"


def test_changed_customers_present_in_one_scenario_only():
    cf = [cf_row(code="1", t12=120000, balance=5000, limit=1000, name="ONE"),
          cf_row(code="30001069", t12=1200000, balance=50000, limit=1000, name="SIAD BULGARIA")]
    d = make_data(cf, [cv_row(code=30001069.0, score="CAUTELA")])
    base = simulate(d, P)
    scen = simulate(d, P.replace(intercompany_codes=[]))
    ch = changed_customers(base, scen).set_index("code")
    x = ch.loc["30001069"]
    assert x["name"] == "SIAD BULGARIA" and x["score_bucket"] == "CAUTELA" and x["exposure"] == 50000
    assert x["current_limit"] == 1000 and x["proposed_limit_base"] == 0 and not x["over_new_base"]
    back = changed_customers(scen, base).set_index("code").loc["30001069"]
    assert back["name"] == "SIAD BULGARIA" and back["exposure"] == 50000


def test_params_lists_normalised():
    p = Params(special_classes=[" s09 ", "ev9", ""], exempt_classes=["a8 "],
               intercompany_codes=[" 30001069.0", "030005389", "30001069", "ABC "])
    assert p.special_classes == ["S09", "EV9"] and p.exempt_classes == ["A8"]
    assert p.intercompany_codes == ["30001069", "30005389", "ABC"]
    q = Params().replace(special_classes=["s09"], intercompany_codes=[30001069.0])
    assert q.special_classes == ["S09"] and q.intercompany_codes == ["30001069"]
    assert Params.from_json(p.to_json()) == p and p.validate() == []
    d = make_data([cf_row(code="70", t12=120000, balance=1, risk=" s09 "),
                   cf_row(code="30001069", t12=120000, balance=1)])
    r = simulate(d, Params().replace(special_classes=["s09"], intercompany_codes=["30001069.0"]))
    assert one(r, "70").reason_code == "R_SPECIAL" and "30001069" not in set(r["code"])


def test_excel_percent_format():
    d = make_data([cf_row(code="1", t12=120000, limit=10000)], [cv_row(code=1.0, fatt=1_000_000)])
    b = to_excel(simulate(d, P), P, "en")
    ws = openpyxl.load_workbook(io.BytesIO(b)).worksheets[0]
    head = {c.value: c.column for c in ws[1]}
    from core import texts as T
    for key in ("diff_pct", "plausibility_ratio"):
        cell = ws.cell(row=2, column=head[T.COLUMN_TEXTS[key][1]])
        assert "%" in cell.number_format, (key, cell.number_format)
    assert "%" not in ws.cell(row=2, column=head[T.COLUMN_TEXTS["proposed_limit"][1]]).number_format


def test_customer_codes_normalised_across_files():
    assert code_to_str(" 0030001 ") == "30001" and code_to_str("30002.0") == "30002"
    assert code_to_str(30003) == "30003" and code_to_str("30 004") == "30004"
    assert code_to_str("AB01") == "AB01" and code_to_str("0") == "0"
    cf = [cf_row(code=" 0030001 ", t12=120000, balance=10), cf_row(code="30002.0", t12=120000, balance=10),
          cf_row(code=30003, t12=120000, balance=10)]
    cv = [cv_row(code=30001.0, fido=1000), cv_row(code="30002", fido=2000), cv_row(code=" 0030003 ", fido=3000)]
    ar = [ar_row("0030001", "2026-06-01", "2026-07-01", 100, "2026-07-01"),
          ar_row(30002.0, "2026-06-01", "2026-07-01", 100, "2026-07-01"),
          ar_row(" 30003", "2026-06-01", "2026-07-01", 100, "2026-07-01")]
    r = simulate(make_data(cf, cv, ar), P)
    assert sorted(r["code"]) == ["30001", "30002", "30003"]
    assert r["in_cerved"].all() and (r["n_invoices"] == 1).all()
    assert r.set_index("code")["ceiling"].to_dict() == {"30001": 1000, "30002": 2000, "30003": 3000}
