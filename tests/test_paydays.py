"""Payment days: per-invoice days, weighted median, window, terms, min / cap, fallback."""
import numpy as np
import pandas as pd

from core.engine import payment_days, simulate, weighted_median
from core.params import Params, OLD_V3
from tests.helpers import REF, ar_row, cf_row, make_data, one

P = Params(reference_date=REF, **OLD_V3)  # unit tests of the v3 mechanics (v3.1: see test_behaviour)


def _pd(rows, window=12):
    d = make_data([cf_row(code="1", t12=1)], ar=rows)
    return payment_days(d.ar, pd.Timestamp(REF), window)


def test_paid_open_overdue_open_not_due():
    # paid in 40 days; open overdue since 100 days; open not due with terms 60
    rows = [ar_row(1, "2026-06-01", "2026-07-01", 100, "2026-07-11")]
    assert _pd(rows).loc["1", "days_measured"] == 40
    rows = [ar_row(1, "2026-08-12", "2026-09-11", 100)]          # due before ref, still open
    assert _pd(rows).loc["1", "days_measured"] == (pd.Timestamp(REF) - pd.Timestamp("2026-08-12")).days
    rows = [ar_row(1, "2026-11-01", "2026-12-31", 100)]          # not yet due
    assert _pd(rows).loc["1", "days_measured"] == 60


def test_weighted_median():
    assert weighted_median(np.array([10, 50, 90]), np.array([1, 1, 10])) == 90
    assert weighted_median(np.array([10, 50, 90]), np.array([5, 1, 1])) == 10
    # cumulated weight reaches exactly half at 50 -> 50
    assert weighted_median(np.array([90, 10, 50]), np.array([2, 1, 1])) == 50
    rows = [ar_row(1, "2026-06-01", "2026-07-01", 100, "2026-06-11"),   # 10 days, 100
            ar_row(1, "2026-06-01", "2026-07-01", 100, "2026-07-21"),   # 50 days, 100
            ar_row(1, "2026-06-01", "2026-07-01", 1000, "2026-08-30")]  # 90 days, 1000
    assert _pd(rows).loc["1", "days_measured"] == 90


def test_window_and_amount_filters():
    rows = [ar_row(1, "2025-11-20", "2025-12-20", 100, "2026-02-18"),   # exactly 12 months ago: out
            ar_row(1, "2025-11-21", "2025-12-21", 100, "2025-12-11"),   # in: 20 days
            ar_row(1, "2026-06-01", "2026-07-01", -500, "2026-12-01"),  # credit note: out
            ar_row(1, "2026-06-01", "2026-07-01", 0, "2026-12-01")]     # zero: out
    r = _pd(rows)
    assert r.loc["1", "days_measured"] == 20 and r.loc["1", "n_invoices"] == 1
    # terms: median of (due - invoice) over ALL rows of the customer (30, 30, 30, 30)
    assert r.loc["1", "days_terms"] == 30


def test_total_rows_dropped_and_terms_median():
    rows = [ar_row(1, "2026-06-01", "2026-07-01", 100, "2026-07-01"),
            ar_row(1, "2026-06-01", "2026-08-30", 100, "2026-07-01"),
            ar_row(1, "2026-06-01", "2026-09-29", 100, "2026-07-01"),
            ar_row("Total 1", "2026-06-01", "2026-07-01", 300)]
    d = make_data([cf_row(code="1", t12=1)], ar=rows)
    assert len(d.ar) == 3
    assert any(f.code == "AR_TOTAL_ROWS_DROPPED" and f.count == 1 for f in d.findings)
    assert payment_days(d.ar, pd.Timestamp(REF), 12).loc["1", "days_terms"] == 90


def test_min_cap_and_fallback():
    cf = [cf_row(code="1", t12=120000), cf_row(code="2", t12=120000),
          cf_row(code="3", t12=120000), cf_row(code="4", t12=120000)]
    ar = [ar_row(1, "2026-06-01", "2026-06-06", 100, "2026-06-06"),    # 5 days, terms 5 -> min 15
          ar_row(2, "2026-06-01", "2026-07-01", 100, "2026-09-29"),    # 120 days, terms 30 -> cap 45
          ar_row(3, "2026-06-01", "2026-06-11", 100, "2026-09-29")]    # 120 days, terms 10 -> 15+15
    d = make_data(cf, ar=ar)
    r = simulate(d, P)
    a, b, c, e = (one(r, x) for x in "1234")
    assert a.days_used == 15 and a.days_min_applied and not a.days_capped
    assert b.days_used == 45 and b.days_capped and b.days_max == 45
    assert c.days_used == 30 and c.days_capped   # terms 10 floored to 15, + 15
    assert e.days_source == "fallback" and e.days_used == 30
    r2 = simulate(d, P.replace(cap_days_enabled=False))
    assert one(r2, "2").days_used == 120
    r3 = simulate(d, P.replace(fallback_days=60, cap_extra_days=0))
    assert one(r3, "4").days_used == 60


def test_customer_invoices_matches_payment_days():
    """engine.customer_invoices (Customer page) uses the same invoices and days as payment_days."""
    from core.engine import customer_invoices
    rows = [ar_row(1, "2025-11-20", "2025-12-20", 100, "2026-02-18"),   # outside the window
            ar_row(1, "2026-06-01", "2026-07-01", 100, "2026-06-11"),   # paid, 10 days
            ar_row(1, "2026-06-01", "2026-07-01", -50, "2026-06-11"),   # credit note: ignored
            ar_row(1, "2026-08-12", "2026-09-11", 300),                 # open overdue
            ar_row(1, "2026-11-01", "2026-12-31", 100),                 # open not due: 60
            ar_row(2, "2026-06-01", "2026-07-01", 100, "2026-06-11")]   # other customer
    d = make_data([cf_row(code="1", t12=1), cf_row(code="2", t12=1)], ar=rows)
    inv = customer_invoices(d.ar, "1", pd.Timestamp(REF), 12)
    assert len(inv) == 3 and inv["invoice_date"].is_monotonic_increasing
    assert inv["days"].tolist() == [10, (pd.Timestamp(REF) - pd.Timestamp("2026-08-12")).days, 60]
    assert inv["is_open"].tolist() == [False, True, True]
    pdays = payment_days(d.ar, pd.Timestamp(REF), 12).loc["1"]
    assert weighted_median(inv["days"].to_numpy(), inv["amount"].to_numpy()) == pdays["days_measured"]
    assert len(inv) == pdays["n_invoices"]
    assert customer_invoices(None, "1", pd.Timestamp(REF), 12).empty
    assert customer_invoices(d.ar, "999", pd.Timestamp(REF), 12).empty
