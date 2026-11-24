"""Vectorised credit-limit calculation (SPEC section 4). No UI dependencies.

``simulate(data, params)`` returns one row per active, non-intercompany customer with
every intermediate value. Payment days are computed by ``payment_days`` and cached on
the ``LoadedData`` object (they depend only on AR124, reference date and window).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .loaders import LOCAL_CURRENCY, LoadedData
from .params import DAYS_MEASURED, Params, ROUND_UP
from . import explain

SCORE_RELIABLE, SCORE_CAUTION, SCORE_MAX = "AFFIDABILE", "CAUTELA", "MASSIMA CAUTELA"
BUCKET_NONE = "NONE"  # not in Cerved, or in Cerved without score
BUCKETS = [SCORE_RELIABLE, SCORE_CAUTION, SCORE_MAX, BUCKET_NONE]
EQUAL_TOLERANCE = 0.5  # RON: proposed and current limits closer than this are "equal"
BAND_BONUS, BAND_TOLERANCE, BAND_MALUS, BAND_NONE = "BONUS", "TOLERANCE", "MALUS", "NONE"
# v3.2: measured days exist but the bonus / malus is not applied (0%): new customer (or no history),
# or fewer than ``behaviour_min_invoices`` invoices already due
BAND_NEW_CUSTOMER, BAND_FEW_INVOICES = "NEW_CUSTOMER", "FEW_INVOICES"
BEHAVIOUR_BANDS = [BAND_BONUS, BAND_TOLERANCE, BAND_MALUS, BAND_NEW_CUSTOMER, BAND_FEW_INVOICES, BAND_NONE]
# Customer age bands (v3.2)
AGE_NEW, AGE_YOUNG, AGE_CONSOLIDATED, AGE_NO_HISTORY = "NEW", "YOUNG", "CONSOLIDATED", "NO_HISTORY"
AGE_BANDS = [AGE_NEW, AGE_YOUNG, AGE_CONSOLIDATED, AGE_NO_HISTORY]
MAX_MONTHS_ACTIVE = 12.0   # the turnover is a 12-month figure: never divided by more than 12 months


def behaviour_pct(delay: np.ndarray, params: Params) -> tuple[np.ndarray, np.ndarray]:
    """Payment-behaviour bonus / malus per customer: (pct as a fraction, band code).

    delay = measured days - contractual terms (NaN without measured days -> 0%, band NONE).
    delay <= 0 -> +bonus_max (BONUS); 0 < delay <= tolerance -> 0 (TOLERANCE); beyond the
    tolerance the malus grows linearly from 0 at tolerance_days to -malus_max at
    full_malus_days and stays there (MALUS). Option off -> 0% and NONE for everybody.
    """
    d = np.asarray(delay, dtype=float)
    n = len(d)
    if not params.behaviour_enabled:
        return np.zeros(n), np.full(n, BAND_NONE, dtype=object)
    has = ~np.isnan(d)
    tol, full = float(params.behaviour_tolerance_days), float(params.behaviour_full_malus_days)
    with np.errstate(invalid="ignore"):
        share = np.clip((d - tol) / (full - tol), 0.0, 1.0)
        bonus, tolerance = has & (d <= 0), has & (d > 0) & (d <= tol)
    malus = has & ~bonus & ~tolerance
    pct = np.select([bonus, malus], [float(params.behaviour_bonus_max),
                                     -float(params.behaviour_malus_max) * np.nan_to_num(share)], 0.0)
    pct = np.round(pct, 12) + 0.0   # float noise off; -0.0 -> 0.0
    band = np.select([bonus, tolerance, malus], [BAND_BONUS, BAND_TOLERANCE, BAND_MALUS], BAND_NONE).astype(object)
    return pct, band


def months_between(start: Any, end: Any) -> float:
    """Calendar months from ``start`` to ``end`` (fractional): whole months by calendar date, plus the
    share of the next month reached. 20/11/2025 -> 20/11/2026 = 12; 20/08/2026 -> 20/11/2026 = 3;
    21/11/2025 -> 20/11/2026 = 11 + 30/31. NaN for a missing date; 0 when start >= end."""
    if start is None or pd.isna(start) or end is None or pd.isna(end):
        return float("nan")
    a, b = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if a >= b:
        return 0.0
    n = (b.year - a.year) * 12 + (b.month - a.month)
    anchor = a + pd.DateOffset(months=n)
    if anchor > b:
        n -= 1
        anchor = a + pd.DateOffset(months=n)
    nxt = a + pd.DateOffset(months=n + 1)
    return round(n + (b - anchor).days / (nxt - anchor).days, 6)


def age_band(age: np.ndarray, params: Params, censored: np.ndarray | None = None) -> np.ndarray:
    """Customer-age band per customer: NO_HISTORY (no invoice, age NaN), NEW (age < new_customer_months),
    YOUNG (new <= age < consolidated_months), CONSOLIDATED (age >= consolidated_months). The band is
    computed whether or not the banding is on; it changes the formula only with ``age_bands_enabled``.
    ``censored`` (age from a first AR124 invoice within 31 days of the file start): CONSOLIDATED."""
    a = np.asarray(age, dtype=float)
    has = ~np.isnan(a)
    with np.errstate(invalid="ignore"):
        new = has & (a < float(params.new_customer_months))
        young = has & ~new & (a < float(params.consolidated_months))
    if censored is not None:   # age "at least N months" (first invoice at the start of AR124): consolidated
        cen = np.asarray(censored, dtype=bool)
        new, young = new & ~cen, young & ~cen
    return np.select([~has, new, young], [AGE_NO_HISTORY, AGE_NEW, AGE_YOUNG], AGE_CONSOLIDATED).astype(object)


def months_active(age: np.ndarray, band: np.ndarray, params: Params) -> np.ndarray:
    """Months the 12-month turnover is divided by: NEW / YOUNG with the banding on -> the age, at least
    1 and at most 12; everybody else (and everybody with the banding off) -> 12."""
    a = np.asarray(age, dtype=float)
    b = pd.Series(np.asarray(band, dtype=object))
    annualise = bool(params.age_bands_enabled) & b.isin([AGE_NEW, AGE_YOUNG]).to_numpy()
    return np.where(annualise, np.clip(np.nan_to_num(a, nan=MAX_MONTHS_ACTIVE), 1.0, MAX_MONTHS_ACTIVE),
                    MAX_MONTHS_ACTIVE)


def _finish(limit: np.ndarray, zero: np.ndarray, ceil_eff: np.ndarray, ceil_unit: np.ndarray,
            p: Params) -> dict[str, np.ndarray]:
    """Cerved ceiling, zeroing, rounding, minimum and hard ceiling applied to ``limit`` (the limit
    after risk factor and payment behaviour). Returns the engine columns of these steps."""
    out: dict[str, np.ndarray] = {}
    out["ceiling_binds"] = ceil_eff < limit
    after_ceiling = np.minimum(limit, ceil_eff)
    out["limit_after_ceiling"] = after_ceiling
    pre = np.where(zero, 0.0, after_ceiling)
    out["limit_before_rounding"] = pre
    step = float(p.rounding_step)
    # round to 1/1000 RON first so float noise (220000.00000000003) does not round up a full step
    q = np.round(pre / step, 9)
    rounded = (np.ceil(q) if p.rounding_mode == ROUND_UP else np.floor(q)) * step
    out["limit_rounded"] = rounded
    min_applied = (rounded > 0) & (rounded < p.min_limit)
    prop = np.where(min_applied, float(p.min_limit), rounded)
    out["limit_after_minimum"] = prop
    # hard Cerved cap (rule 8): final = min(rounded limit with minimum, ceiling in whole RON). The
    # ceiling is not floored to the rounding step, so rounding up and the minimum never go
    # above it and the minimum never lifts a limit above it; ceiling 0 -> 0.
    if p.ceiling_is_hard:
        capped = np.minimum(prop, ceil_unit)
        hard = capped < prop
        prop = capped
    else:
        hard = np.zeros(len(limit), bool)
    out["hard_cap_applied"] = hard
    out["min_applied"] = min_applied & ~hard
    out["proposed_limit"] = prop
    return out


# ---------------------------------------------------------------------------
# Payment days
# ---------------------------------------------------------------------------
def reference_date(data: LoadedData, params: Params) -> pd.Timestamp:
    """Parameter if set, else latest AR124 invoice date, else today."""
    if params.reference_date:
        return pd.Timestamp(params.reference_date).normalize()
    d = data.default_reference_date
    return d if d is not None else pd.Timestamp.today().normalize()


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Sort by value; return the first value where cumulated weight reaches half the total."""
    o = np.argsort(values, kind="mergesort")
    v, c = np.asarray(values, float)[o], np.cumsum(np.asarray(weights, float)[o])
    return float(v[np.searchsorted(c, c[-1] / 2)])


def _invoice_days(inv: pd.Series, due: pd.Series, closed: pd.Series, ref: pd.Timestamp) -> np.ndarray:
    """Days per invoice as seen at the reference date (no look-ahead).

    An invoice closed after the reference date was still open at the reference date.
    paid (closed <= ref) -> closed - invoice; open and overdue (due < ref) -> ref - invoice;
    open not yet due -> due - invoice (assumed paid at terms).
    """
    paid = closed.notna() & (closed <= ref)
    return np.where(paid, (closed - inv).dt.days,
                    np.where(due < ref, (ref - inv).dt.days, (due - inv).dt.days))


def payment_days(ar: pd.DataFrame | None, ref_date: pd.Timestamp, window_months: int,
                 terms_positive_only: bool = True) -> pd.DataFrame:
    """Per customer: ``days_measured`` (amount-weighted median), ``days_terms`` (median of
    due - invoice), ``n_invoices`` / ``amount_invoices`` used for the measure.

    Invoices used for the measure: invoice date in (ref - window, ref], amount > 0. Days per
    invoice: see ``_invoice_days`` (closing dates after the reference date are ignored).
    Contractual terms: invoices dated up to the reference date, amount > 0 only (credit notes
    excluded); ``terms_positive_only=False`` = the legacy rule: every row of the file, whatever
    its date or sign.
    """
    cols = ["days_measured", "days_terms", "n_invoices", "amount_invoices"]
    if ar is None or ar.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="customer"), dtype=float)
    ref = pd.Timestamp(ref_date)
    start = ref - pd.DateOffset(months=int(window_months))
    inv, due, closed = ar["invoice_date"], ar["due_date"], ar["closed_date"]
    sel = ((inv > start) & (inv <= ref) & (ar["amount"] > 0)).to_numpy(bool)
    a = ar.loc[sel, ["customer", "amount"]].copy()
    a["d"] = _invoice_days(inv[sel], due[sel], closed[sel], ref)
    a = a[a["d"].notna()]
    # vectorised weighted median: sort by customer, days; first row with cum >= total/2
    a = a.sort_values(["customer", "d"], kind="mergesort")
    g = a.groupby("customer", sort=False)["amount"]
    cum = g.cumsum()
    half = g.transform("sum") / 2
    hit = a[cum.values >= half.values]
    meas = hit.drop_duplicates("customer", keep="first").set_index("customer")["d"].astype(float)
    stats = a.groupby("customer")["amount"].agg(["size", "sum"])
    t = (due - inv).dt.days
    if terms_positive_only:
        tsel = t.notna() & (inv <= ref) & (ar["amount"] > 0)
    else:  # legacy rule: every row of the file, any date and any sign (credit notes included)
        tsel = t.notna()
    tsel = tsel.to_numpy(bool)
    terms = t[tsel].groupby(ar.loc[tsel, "customer"]).median()
    out = pd.DataFrame({"days_measured": meas}).join(terms.rename("days_terms"), how="outer")
    out = out.join(stats.rename(columns={"size": "n_invoices", "sum": "amount_invoices"}), how="left")
    out[["n_invoices", "amount_invoices"]] = out[["n_invoices", "amount_invoices"]].fillna(0)
    out.index.name = "customer"
    return out[cols].astype(float)


def customer_invoices(ar: pd.DataFrame | None, code: str, ref_date: pd.Timestamp,
                      window_months: int) -> pd.DataFrame:
    """The invoices of one customer that ``payment_days`` uses, with the days counted for each.

    Same selection and day rules as ``payment_days`` (window, amount > 0; paid / open overdue /
    open not due, as seen at the reference date). Columns: invoice_date, due_date, closed_date,
    amount, days, is_open (open at the reference date). Sorted by invoice date.
    Empty frame without AR124 or invoices.
    """
    cols = ["invoice_date", "due_date", "closed_date", "amount", "days", "is_open"]
    if ar is None or ar.empty:
        return pd.DataFrame(columns=cols)
    from .loaders import code_to_str
    ref = pd.Timestamp(ref_date)
    start = ref - pd.DateOffset(months=int(window_months))
    a = ar[ar["customer"] == code_to_str(code)]
    a = a[((a["invoice_date"] > start) & (a["invoice_date"] <= ref) & (a["amount"] > 0)).to_numpy(bool)]
    i, d, c = a["invoice_date"], a["due_date"], a["closed_date"]
    days = _invoice_days(i, d, c, ref)
    out = pd.DataFrame({"invoice_date": i, "due_date": d, "closed_date": c,
                        "amount": a["amount"], "days": days, "is_open": ~(c.notna() & (c <= ref))})
    return out[out["days"].notna()].sort_values("invoice_date", kind="mergesort").reset_index(drop=True)[cols]


GAP_MIN_EMPTY_MONTHS = 3   # purchase-gap note on the Customer page from this many months without invoices


def purchase_months(ar: pd.DataFrame | None, code: str, ref_date: pd.Timestamp, months: int = 12,
                    overdue_grace_days: int = 0) -> pd.DataFrame:
    """One customer's last ``months`` calendar months (1st to last day; the reference month runs to the
    reference date): invoiced amount and highest open balance of the month (AR124).

    ``amount``: invoices with amount > 0 dated in the month (credit notes out).
    ``peak_open``: highest balance of open items on any day of the month: every invoice / credit note
    counts from its issue date until it is closed, also in the following months and when overdue. In
    Romania deliveries are invoiced at once, so this is the exposure the order check would have seen,
    except orders not yet delivered and open items older than the AR124 file.
    ``peak_overdue``: highest overdue amount of the month: open items more than ``overdue_grace_days``
    past their due date on that day (the page passes the bonus/malus tolerance, 5 days, so an invoice
    paid a day or two late does not show as overdue). ``partial``: the month is not over at the reference date.
    Columns: month (first day), end, amount, peak_open, partial. Oldest first. Empty frame without AR124.
    """
    cols = ["month", "end", "amount", "peak_open", "peak_overdue", "partial"]
    if ar is None or ar.empty:
        return pd.DataFrame(columns=cols)
    from .loaders import code_to_str
    ref = pd.Timestamp(ref_date).normalize()
    a = ar[ar["customer"] == code_to_str(code)]
    a = a[a["invoice_date"].notna() & (a["invoice_date"] <= ref)]
    first = (ref.to_period("M") - (months - 1)).to_timestamp()
    days = pd.date_range(first, ref, freq="D")
    if len(a):
        inv = a["invoice_date"].to_numpy("datetime64[ns]")
        clo = a["closed_date"].fillna(pd.Timestamp.max.normalize()).to_numpy("datetime64[ns]")
        amt = a["amount"].to_numpy(float)
        d = days.to_numpy("datetime64[ns]")[:, None]
        due = a["due_date"].fillna(pd.Timestamp.max.normalize()).to_numpy("datetime64[ns]")
        is_open = (inv[None, :] <= d) & (clo[None, :] > d)
        daily = pd.Series((is_open * amt[None, :]).sum(axis=1), index=days)
        daily_od = pd.Series((is_open & ((due + np.timedelta64(int(overdue_grace_days), "D"))[None, :] < d)).astype(float) @ amt, index=days)
    else:
        daily = pd.Series(0.0, index=days)
        daily_od = pd.Series(0.0, index=days)
    rows = []
    for k in range(months):
        m0 = (first.to_period("M") + k).to_timestamp()
        m1 = min((m0.to_period("M") + 1).to_timestamp() - pd.Timedelta(days=1), ref)
        inm = (a["invoice_date"] >= m0) & (a["invoice_date"] <= m1) & (a["amount"] > 0)
        peak = float(daily.loc[m0:m1].max()) if len(daily.loc[m0:m1]) else 0.0
        peak_od = float(daily_od.loc[m0:m1].max()) if len(daily_od.loc[m0:m1]) else 0.0
        rows.append((m0, m1, float(a.loc[inm.to_numpy(bool), "amount"].sum()), max(peak, 0.0), max(peak_od, 0.0),
                     m1 < (m0.to_period("M") + 1).to_timestamp() - pd.Timedelta(days=1)))
    return pd.DataFrame(rows, columns=cols)


def blocked_months(pm: pd.DataFrame, limit: float) -> list[bool]:
    """Months in which the open balance went above ``limit``: an order entered then would have been held."""
    return [bool(x > limit + 0.005) for x in pm["peak_open"]]


def purchase_gap_effect(row: pd.Series, pm: pd.DataFrame, params: Params | None = None) -> dict[str, Any] | None:
    """How much months without purchases lower this customer's limit. Explanation only: the formula
    is not changed.

    Applies when the monthly turnover is the 12-month turnover / 12 (consolidated customers, or age
    bands off), the limit is > 0 and at least ``GAP_MIN_EMPTY_MONTHS`` of the 12 periods have no
    invoices. Returns the months with / without purchases, the 12-month average, the average of the
    months with purchases and the limit that average would give (same steps 4-11), or None.
    """
    p = params or Params()
    if pm is None or pm.empty:
        return None
    t12 = float(row.get("turnover_12m") or 0)
    used = float(row.get("monthly_revenue_used") or 0)
    n = len(pm)
    bought = int((pm["amount"] > 0).sum())
    empty = n - bought
    if t12 <= 0 or used <= 0 or bought == 0 or empty < GAP_MIN_EMPTY_MONTHS:
        return None
    if abs(used - t12 / n) > 0.01 * used:          # young / new customers: already divided by months active
        return None
    if float(row.get("proposed_limit") or 0) <= 0 or float(row.get("limit_after_behaviour") or 0) <= 0:
        return None
    alt_monthly = t12 / bought
    raw = float(row["limit_after_behaviour"]) * alt_monthly / used
    ceil = row.get("ceiling")
    ceil_unit = row.get("ceiling_unit")
    ceil = np.inf if ceil is None or pd.isna(ceil) else float(ceil)
    ceil_unit = np.inf if ceil_unit is None or pd.isna(ceil_unit) else float(ceil_unit)
    alt = float(_finish(np.array([raw]), np.array([False]), np.array([ceil]), np.array([ceil_unit]), p)
                ["proposed_limit"][0])
    return {"months": n, "bought": bought, "empty": empty,
            "empty_mask": (pm["amount"] <= 0).tolist(), "monthly_12": t12 / n, "monthly_bought": alt_monthly,
            "limit_alt": alt, "limit": float(row["proposed_limit"]), "ceiling_binds": raw > ceil}


EARLIER_INVOICE_DAYS = 31   # first AR124 invoice more than this before the MD105 opening date -> use the invoice
AGE_SRC_MD105, AGE_SRC_INVOICE_EARLIER, AGE_SRC_AR124 = "md105", "ar124_earlier", "ar124"


def customer_history(ar: pd.DataFrame | None, ref_date: pd.Timestamp, window_months: int,
                     md105: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per customer (v3.2): the start date of the customer age and the invoices already due.

    - ``opened_date``: account opening date from the customer master MD105 (optional file).
    - ``first_invoice_date``: first invoice with amount > 0 in the WHOLE AR124 file (no window) dated up
      to the reference date.
    - ``age_start_date`` / ``age_source``: the MD105 opening date (``md105``); the first invoice when it is
      more than 31 days earlier than the opening date (``ar124_earlier``: code re-created in JDE); without
      MD105 or for a customer missing in it, the first invoice (``ar124``); NaN when neither exists.
    - ``age_months`` = calendar months from the start date to the reference date (``months_between``;
      an opening date after the reference date gives 0).
    - ``behaviour_invoices_n`` = invoices with amount > 0 in the payment-days window (invoice date in
      (ref - window, ref]) already due by the reference date (due date <= ref): the base of the
      ``behaviour_min_invoices`` gate.
    """
    cols = ["opened_date", "first_invoice_date", "age_start_date", "age_source", "age_months",
            "behaviour_invoices_n", "age_censored", "ar_start_date"]
    ref = pd.Timestamp(ref_date)
    parts = []
    if ar is not None and not ar.empty:
        inv, due = ar["invoice_date"], ar["due_date"]
        sel = (ar["amount"] > 0).to_numpy(bool) & (inv <= ref).to_numpy(bool)
        parts.append(inv[sel].groupby(ar.loc[sel, "customer"]).min().rename("first_invoice_date"))
        start = ref - pd.DateOffset(months=int(window_months))
        dsel = sel & (inv > start).to_numpy(bool) & (due <= ref).to_numpy(bool)
        parts.append(ar.loc[dsel, "customer"].value_counts().rename("behaviour_invoices_n"))
    if md105 is not None and not md105.empty:
        m = md105[md105["opened_date"].notna()]
        parts.append(m.set_index("customer")["opened_date"].rename("opened_date"))
    if not parts:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="customer"))
    out = pd.concat(parts, axis=1)
    for c in cols:
        if c not in out:
            out[c] = np.nan
    out["opened_date"] = pd.to_datetime(out["opened_date"])
    out["first_invoice_date"] = pd.to_datetime(out["first_invoice_date"])
    op, fi = out["opened_date"], out["first_invoice_date"]
    earlier = op.notna() & fi.notna() & ((op - fi).dt.days > EARLIER_INVOICE_DAYS)
    out["age_start_date"] = op.where(op.notna() & ~earlier, fi)
    out["age_source"] = np.select([op.notna() & ~earlier, earlier, fi.notna()],
                                  [AGE_SRC_MD105, AGE_SRC_INVOICE_EARLIER, AGE_SRC_AR124], "").astype(object)
    out.loc[out["age_source"] == "", "age_source"] = np.nan
    starts = out["age_start_date"].dropna().unique()
    ages = {d: months_between(d, ref) for d in starts}
    out["age_months"] = out["age_start_date"].map(ages).astype(float)
    out["behaviour_invoices_n"] = out["behaviour_invoices_n"].fillna(0).astype(float)
    # left-censoring: an age taken from the first AR124 invoice cannot prove the customer is young when that
    # invoice is within 31 days of the start of the file (it may have bought before the file starts)
    ar_start = None
    if ar is not None and not ar.empty and ar["invoice_date"].notna().any():
        ar_start = pd.Timestamp(ar["invoice_date"].min()).normalize()
    from_inv = out["age_source"].isin([AGE_SRC_AR124, AGE_SRC_INVOICE_EARLIER])
    out["age_censored"] = (from_inv & out["age_start_date"].notna()
                           & ((out["age_start_date"] - ar_start).dt.days <= EARLIER_INVOICE_DAYS)
                           if ar_start is not None else False)
    out["age_censored"] = out["age_censored"].fillna(False).astype(bool)
    out["ar_start_date"] = ar_start
    out.index.name = "customer"
    return out[cols]


def ar_coverage_months(ar: pd.DataFrame | None) -> float | None:
    """Months covered by the AR124 file: earliest to latest invoice date (``months_between``).
    None without AR124 or without invoice dates."""
    if ar is None or ar.empty or ar["invoice_date"].notna().sum() == 0:
        return None
    return months_between(ar["invoice_date"].min(), ar["invoice_date"].max())


def coverage_finding(data: LoadedData, params: Params) -> Any:
    """Data-quality finding AR_SHORT_HISTORY when the customer-age bands are on, the customer master
    MD105 is NOT loaded (so ages come from the first AR124 invoice) and AR124 covers less than
    ``consolidated_months`` + 6 months: a customer whose first invoice falls in that period may be an
    occasional buyer rather than a new one. None otherwise (with MD105 no warning; the banding is never
    switched off silently: the finding and the page banners say it). Details: months, needed."""
    from .loaders import Finding
    if not params.age_bands_enabled or data.md105 is not None:
        return None
    cov = ar_coverage_months(data.ar)
    needed = int(params.consolidated_months) + 6
    if cov is None or cov >= needed:
        return None
    return Finding("AR_SHORT_HISTORY", "warning", 1, [], {"months": cov, "needed": needed})


def age_findings(result: pd.DataFrame, data: LoadedData, params: Params) -> list[Any]:
    """Customer-age findings on a simulation result (active customers), age bands on and MD105 loaded:
    AGE_INVOICE_BEFORE_OPENING (first AR124 invoice more than 31 days before the MD105 opening date: the
    earlier date is used; examples = codes, details ``codes``) and MD_CUSTOMER_MISSING (customers not in
    MD105: age from AR124; details ``codes``). Counts on the order-check scope (``details["scope_n"]``)
    and on all active customers (``count``)."""
    from .loaders import Finding
    if not params.age_bands_enabled or data.md105 is None or "age_source" not in result:
        return []
    out = []
    for code, mask in (("AGE_INVOICE_BEFORE_OPENING", result["age_source"].eq(AGE_SRC_INVOICE_EARLIER)),
                       ("MD_CUSTOMER_MISSING", result["opened_date"].isna())):
        m = mask.to_numpy(bool)
        if m.any():
            codes = result.loc[m, "code"].tolist()
            out.append(Finding(code, "info" if code == "AGE_INVOICE_BEFORE_OPENING" else "warning", int(m.sum()),
                               codes[:20], {"codes": codes,
                                            "scope_n": int((m & result["in_scope"].to_numpy(bool)).sum())}))
    return out


def cached_history(data: LoadedData, params: Params) -> pd.DataFrame:
    """``customer_history`` memoised on the data object by (reference date, window)."""
    ref = reference_date(data, params)
    key = ("history", ref, int(params.window_months))
    if key not in data.cache:
        data.cache[key] = customer_history(data.ar, ref, params.window_months, data.md105)
    return data.cache[key]


def cached_payment_days(data: LoadedData, params: Params) -> pd.DataFrame:
    """``payment_days`` memoised on the data object by (reference date, window, terms rule)."""
    ref = reference_date(data, params)
    key = ("payment_days", ref, int(params.window_months), bool(params.terms_positive_only))
    if key not in data.cache:
        data.cache[key] = payment_days(data.ar, ref, params.window_months, params.terms_positive_only)
    return data.cache[key]


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
def simulate(data: LoadedData, params: Params | None = None, include_all: bool = False) -> pd.DataFrame:
    """Proposed credit limit and controls per customer.

    Returns one row per active customer (Balance != 0 or Turnover 12 months > 0),
    intercompany excluded. With ``include_all`` every Check fidi row is returned, with
    the flags ``is_active`` / ``is_intercompany`` (excluded rows get proposed limit 0).
    """
    p = (params or Params()).check()
    if data.customers is None:
        raise ValueError("Check fidi file missing: no simulation possible.")
    c = data.matched_customers(p.cerved_reject_vat_conflict)
    pdays = cached_payment_days(data, p)
    r = pd.DataFrame({
        "code": c["code"], "name": c["name"], "risk_class": c["risk_class"], "vat": c["vat"],
        "in_cerved": c["in_cerved"], "match_method": c["match_method"], "vat_differs": c["vat_differs"],
        "vat_conflict": c["vat_conflict"],
        "cerved_name": c["cv_name"], "score": c["score"], "reliability_class": c["reliability_class"],
        "cerved_limit_orig": c["cerved_limit"], "cerved_currency": c["currency"],
        "cerved_turnover": c["total_turnover"], "cerved_limit_usable": c["limit_usable"],
        "balance": c["balance"], "overdue": c["overdue"], "ordered": c["ordered"],
        "delivered": c["delivered"], "current_limit": c["credit_limit"], "turnover_12m": c["turnover_12m"],
        "block_description": c["block_description"],
    })
    r["exposure"] = r["balance"] + r["ordered"] + r["delivered"]
    r["is_intercompany"] = r["code"].isin(set(p.intercompany_codes))
    r["is_active"] = (r["balance"] != 0) | (r["turnover_12m"] > 0)
    r["is_special"] = r["risk_class"].isin(set(p.special_classes))
    r["is_exempt"] = r["risk_class"].isin(set(p.exempt_classes)) & ~r["is_special"]
    r["in_scope"] = r["is_active"] & ~r["is_intercompany"] & ~r["is_special"] & ~r["is_exempt"]

    # --- payment days ---
    pdx = pdays.reindex(r["code"])
    meas = pdx["days_measured"].to_numpy()
    terms = pdx["days_terms"].to_numpy()
    r["days_measured"] = meas
    r["days_terms"] = terms
    r["n_invoices"] = pdx["n_invoices"].fillna(0).to_numpy()

    # --- customer age (v3.2): first invoice in the whole AR124, band, months active ---
    hx = cached_history(data, p).reindex(r["code"])
    age = hx["age_months"].to_numpy(dtype=float)
    r["first_invoice_date"] = pd.to_datetime(hx["first_invoice_date"]).to_numpy()
    r["opened_date"] = pd.to_datetime(hx["opened_date"]).to_numpy()
    r["age_start_date"] = pd.to_datetime(hx["age_start_date"]).to_numpy()
    r["age_source"] = hx["age_source"].to_numpy(dtype=object)
    r["age_months"] = age
    r["age_censored"] = hx["age_censored"].fillna(False).to_numpy(dtype=bool)
    r["ar_start_date"] = pd.to_datetime(hx["ar_start_date"]).to_numpy()
    band_age = age_band(age, p, r["age_censored"].to_numpy())
    r["age_band"] = band_age
    r["months_active"] = months_active(age, band_age, p)
    r["behaviour_invoices_n"] = hx["behaviour_invoices_n"].fillna(0).to_numpy(dtype=float)
    r["revenue_check_flag"] = bool(p.age_bands_enabled) & (band_age == AGE_NEW)
    measured_basis = p.m1_days_basis == DAYS_MEASURED
    if measured_basis:   # v3: measured days, else contractual terms, else the fallback days
        r["days_source"] = np.where(~np.isnan(meas), "measured", np.where(~np.isnan(terms), "terms", "fallback"))
        raw = np.where(~np.isnan(meas), meas, np.where(~np.isnan(terms), terms, float(p.fallback_days)))
    else:                # contractual basis: the terms (fallback days without terms); behaviour acts via bonus/malus
        r["days_source"] = np.where(~np.isnan(terms), "contractual", "fallback")
        raw = np.where(~np.isnan(terms), terms, float(p.fallback_days))
    r["days_raw"] = raw
    floored = np.maximum(raw, float(p.min_days))
    r["days_min_applied"] = raw < p.min_days
    terms_for_cap = np.maximum(np.where(np.isnan(terms), float(p.fallback_days), terms), float(p.min_days))
    r["days_max"] = terms_for_cap + p.cap_extra_days if p.cap_days_enabled else np.inf
    used = np.minimum(floored, r["days_max"].to_numpy())
    r["days_capped"] = used < floored
    r["days_used"] = used

    # --- need and base ---
    t12 = r["turnover_12m"].to_numpy()
    # monthly revenue: turnover / 12, or / months active for NEW / YOUNG customers (age bands on)
    r["monthly_revenue_used"] = np.maximum(t12, 0) / r["months_active"].to_numpy()
    r["m1"] = r["monthly_revenue_used"].to_numpy() * (used / 30) * (1 + p.buffer)
    r["base_limit"] = p.multiplier * r["m1"]

    # --- risk coefficient ---
    sc = r["score"]
    has_score = r["in_cerved"] & sc.isin([SCORE_RELIABLE, SCORE_CAUTION, SCORE_MAX])
    r["score_bucket"] = np.where(has_score, sc, BUCKET_NONE)
    b = r["score_bucket"]
    no_cv_coef = np.where(r["is_exempt"], p.coef_exempt_not_in_cerved, p.coef_not_in_cerved)
    r["coefficient"] = np.select([b.eq(SCORE_RELIABLE), b.eq(SCORE_CAUTION), b.eq(SCORE_MAX)],
                                 [p.coef_reliable, p.coef_caution, p.coef_max_caution], no_cv_coef)
    r["limit_after_coef"] = r["base_limit"] * r["coefficient"]

    # --- payment behaviour (bonus / malus): delay = measured days - contractual terms, both as
    # computed from AR124 BEFORE the minimum / terms + X adjustments. Only customers with measured
    # days get it. Applied as x (1 + pct) after the risk factor, before the Cerved ceiling.
    r["delay_days"] = meas - terms
    pct, band = behaviour_pct(r["delay_days"].to_numpy(dtype=float), p)
    # v3.2 gates (0%): new customers / no history with the age bands on, and customers with fewer than
    # behaviour_min_invoices invoices already due; only where a bonus / malus would otherwise be computed
    if p.behaviour_enabled:
        computed = band != BAND_NONE
        g_new = computed & bool(p.age_bands_enabled) & np.isin(band_age, [AGE_NEW, AGE_NO_HISTORY])
        g_few = computed & ~g_new & (r["behaviour_invoices_n"].to_numpy() < float(p.behaviour_min_invoices))
        pct = np.where(g_new | g_few, 0.0, pct)
        band = np.where(g_new, BAND_NEW_CUSTOMER, np.where(g_few, BAND_FEW_INVOICES, band)).astype(object)
    r["behaviour_pct"] = pct
    r["behaviour_band"] = band
    r["limit_after_behaviour"] = r["limit_after_coef"].to_numpy() * (1.0 + pct)

    # --- Cerved ceiling (EUR converted; blank currency = RON; other currencies / negative: none) ---
    cur = r["cerved_currency"]
    lim = r["cerved_limit_orig"].to_numpy(dtype=float)
    r["cerved_limit_ron"] = np.where(cur.eq("EUR"), lim * p.eur_ron,
                                     np.where(cur.isna() | cur.eq(LOCAL_CURRENCY), lim, np.nan))
    has_ceiling = (p.cerved_cap_enabled & r["in_cerved"] & r["cerved_limit_usable"]
                   & r["cerved_limit_ron"].notna()).to_numpy(bool)
    r["ceiling"] = np.where(has_ceiling, r["cerved_limit_ron"], np.nan)
    ceil_v = np.where(has_ceiling, r["cerved_limit_ron"], np.inf)
    # A JDE credit limit is whole RON: the ceiling in whole RON is the Cerved value truncated to the
    # unit (4.582,72 -> 4.582), after rounding to 6 decimals so float noise (49.749,9999999) does
    # not lose a whole RON. With the hard ceiling (default) this is the ceiling used everywhere.
    with np.errstate(invalid="ignore"):
        ceil_unit = np.where(np.isinf(ceil_v), np.inf, np.floor(np.round(ceil_v, 6)))
    r["ceiling_unit"] = np.where(has_ceiling, ceil_unit, np.nan)
    ceil_eff = ceil_unit if p.ceiling_is_hard else ceil_v

    # --- zeroing, rounding, minimum ---
    r["zero_special"] = r["is_special"]
    r["zero_no_turnover"] = (t12 <= 0) & ~r["is_special"]
    zero = (r["is_special"] | (t12 <= 0) | r["is_intercompany"]).to_numpy(bool)
    out = _finish(r["limit_after_behaviour"].to_numpy(), zero, ceil_eff, ceil_unit, p)
    for k, v in out.items():
        r[k] = v
    prop = out["proposed_limit"]
    # the same chain without the bonus / malus: its net effect (0 when the option is off)
    if p.behaviour_enabled:
        prop0 = _finish(r["limit_after_coef"].to_numpy(), zero, ceil_eff, ceil_unit, p)["proposed_limit"]
    else:
        prop0 = prop
    r["proposed_limit_no_behaviour"] = prop0
    r["behaviour_effect"] = prop - prop0

    # --- controls ---
    cl = r["current_limit"].to_numpy()
    expo = r["exposure"].to_numpy()
    scope = r["in_scope"].to_numpy()
    r["over_new"] = scope & (expo > prop)
    r["over_current"] = scope & (expo > cl)
    r["excess_new"] = np.where(r["over_new"], expo - prop, 0.0)
    r["excess_current"] = np.where(r["over_current"], expo - cl, 0.0)
    diff = prop - cl
    r["diff"] = diff
    with np.errstate(divide="ignore", invalid="ignore"):
        r["diff_pct"] = np.where(cl > 0, diff / cl, np.where(np.abs(diff) < EQUAL_TOLERANCE, 0.0, np.inf))
    r["direction"] = np.select([diff >= EQUAL_TOLERANCE, diff <= -EQUAL_TOLERANCE], ["HIGHER", "LOWER"], "EQUAL")
    tot = r["cerved_turnover"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(r["in_cerved"] & (tot > 0), t12 / tot, np.nan)
    r["plausibility_ratio"] = ratio
    r["plausibility_flag"] = np.nan_to_num(ratio, nan=0.0) > p.plausibility_threshold
    # approval: change above the % threshold AND above the materiality amount (both, strictly)
    r["approval_needed"] = ((r["direction"] != "EQUAL") & (np.abs(r["diff_pct"]) > p.approval_threshold)
                            & (np.abs(diff) > p.approval_min_change_ron))
    r["proposed_limit_eur"] = prop / p.eur_ron
    eur = r["proposed_limit_eur"]
    r["tier"] = np.select([eur <= p.tier1_eur, eur <= p.tier2_eur], [1, 2], 3)

    # --- reasons ---
    r["reason_base_code"] = explain.reason_codes(r, behaviour=False)
    r["reason_code"] = explain.age_reasons(r, explain.behaviour_reasons(r, r["reason_base_code"].to_numpy()), p)
    r["change_code"] = explain.change_codes(r)

    if not include_all:
        r = r[r["is_active"] & ~r["is_intercompany"]]
    return r.reset_index(drop=True)
