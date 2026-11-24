"""Regression on the real files in data/ against SPEC section 4.

(a) Legacy parameters (ceiling_is_hard=False, cerved_reject_vat_conflict=False,
    terms_positive_only=False) reproduce the original SPEC 4 reference numbers and, customer
    by customer, the proposed limits of /home/claude/fido_v3_ref/reference_results.parquet.
(b) Default v3 (lead decisions of 20/11/2026: Cerved row with a different VAT not used,
    terms from positive invoices only, hard Cerved ceiling = the ceiling value itself):
    the new reference numbers of SPEC 4.
The EUR rate (4,975 vs 5,0415 in the reference) has no effect on any SPEC number: the
only EUR row (71250113 Air Liquide Bulgaria, 1.300.000 EUR) never binds; it only
moves approval tiers, which are not in the reference.
Skipped (with a message) if the data files are not present.
"""
from __future__ import annotations

import time
from pathlib import Path

from core.engine import simulate
from core.kpi import kpis
from core.loaders import load_folder
from core.params import OLD_V3, V31 as V31_PARAMS, Params

ROOT = Path(__file__).resolve().parents[1]
REF_PARQUET = Path("/home/claude/fido_v3_ref/reference_results.parquet")
_DATA = {}
LEGACY_PARAMS = dict(ceiling_is_hard=False, cerved_reject_vat_conflict=False, terms_positive_only=False, **OLD_V3)

COMMON = {  # identical in both modes
    "n_active": 2116, "n_scope": 1598, "exposure_active": 36.12e6, "limits_current_active": 40.00e6,
    "over_current_n": 267, "excess_current": 9.86e6, "plausibility_n": 22,
    "plausibility_exposure": 2.00e6, "over_new_n_not_in_cerved": 77, "over_new_n_reliable": 38,
}
LEGACY = {"limits_proposed_active": 39.75e6, "over_new_n": 292, "excess_new": 6.97e6,
          "higher_n": 797, "lower_n": 613, "equal_n": 188, "zero_with_turnover_n_active": 168,
          "in_cerved_n_active": 1177, "over_new_n_max_caution": 97, "over_new_n_caution": 80}
V3 = {"limits_proposed_active": 39.71e6, "over_new_n": 290, "excess_new": 6.98e6,
      "higher_n": 796, "lower_n": 614, "equal_n": 188, "zero_with_turnover_n_active": 166,
      "in_cerved_n_active": 1174, "over_new_n_max_caution": 96, "over_new_n_caution": 79,
      "n_not_in_cerved": 446}


def _data():
    if "d" not in _DATA:
        files = list((ROOT / "data").glob("*.xls*"))
        _DATA["d"] = load_folder(ROOT / "data") if len(files) >= 3 else None
    return _DATA["d"]


def _check(k: dict, expected: dict) -> None:
    for key, v in expected.items():
        got = k[key]
        if isinstance(v, float) and v >= 1e5:          # SPEC gives millions with 2 decimals
            assert round(got / 1e6, 2) == round(v / 1e6, 2), (key, got, v)
        else:
            assert got == v, (key, got, v)
    assert round(k["in_cerved_exposure_share_active"], 2) == 0.71


def test_regression_reference_legacy_cap():
    d = _data()
    if d is None:
        print("  (skipped: data files not found)")
        return
    for rate in (4.975, 5.0415):
        r = simulate(d, Params(eur_ron=rate, **LEGACY_PARAMS))
        _check(kpis(r), {**COMMON, **LEGACY})
    if REF_PARQUET.exists():
        import pandas as pd
        ref = pd.read_parquet(REF_PARQUET)
        ref = ref[ref["active"]].set_index("Code")
        mine = r.set_index("code")
        assert set(ref.index) == set(mine.index)
        assert (mine["proposed_limit"] - ref.loc[mine.index, "prop"]).abs().max() == 0
        assert (mine["days_used"] - ref.loc[mine.index, "pdays"]).abs().max() == 0
        assert (mine["in_cerved"] == ref.loc[mine.index, "incerved"]).all()


def test_regression_v3_hard_cap():
    d = _data()
    if d is None:
        print("  (skipped: data files not found)")
        return
    r = simulate(d, Params(**OLD_V3))   # old v3: M1 on measured days, no bonus / malus
    _check(kpis(r), {**COMMON, **V3})
    capped = r[r["ceiling"].notna()]
    assert (capped["proposed_limit"] <= capped["ceiling"]).all()
    x = r.set_index("code")
    # hard ceiling = the ceiling value itself (decision A3)
    assert x.loc["30001755", "proposed_limit"] == 867 and x.loc["30001755", "reason_code"] == "R_CERVED_CAP"
    assert x.loc["71856834", "proposed_limit"] == 4582            # ceiling 4.582,72 -> whole RON
    assert (r["proposed_limit"] % 1 == 0).all()                    # every limit is whole RON
    # Cerved row with a different VAT not used (decision A1)
    assert not x.loc["71782284", "in_cerved"] and x.loc["71782284", "vat_conflict"]
    # every customer whose final limit equals its ceiling says "limited by Cerved"
    eq = capped[(capped["proposed_limit"] == capped["ceiling_unit"]) & (capped["ceiling"] >= 1)
                & ~capped["is_special"] & (capped["turnover_12m"] > 0) & (capped["coefficient"] > 0)]
    assert set(eq["reason_code"]) == {"R_CERVED_CAP"}, eq["reason_code"].value_counts()
    # changes vs the legacy run: only customers touched by the three decisions
    leg = simulate(d, Params(**LEGACY_PARAMS)).set_index("code")
    assert ((x["proposed_limit"] - leg["proposed_limit"]).abs() > 0.4).sum() > 0
    t = time.perf_counter()
    for _ in range(5):
        simulate(d, Params(multiplier=2.5))      # v3.1 default (two passes: with / without bonus)
    assert (time.perf_counter() - t) / 5 < 1.0


V31 = {  # v3.1 default (decision of 21/11/2026): M1 on contractual terms + payment bonus / malus
    "n_active": 2116, "n_scope": 1598, "limits_proposed_active": 39_970_630, "limits_proposed_scope": 33_027_630,
    "over_new_n": 290, "over_new_positive_n": 130, "over_new_zero_n": 160, "excess_new": 7_179_299.29,
    "higher_n": 796, "lower_n": 625, "equal_n": 177, "approval_n": 425, "zero_with_turnover_n_active": 166,
    "behaviour_bonus_n": 868, "behaviour_tolerance_n": 240, "behaviour_malus_n": 435, "behaviour_no_history_n": 55,
    "behaviour_effect_active": 414_000, "behaviour_effect_scope": 340_000, "days_capped_n": 0,
    "over_current_n": 267, "over_current_positive_n": 202,
}
OLD_V3_EXACT = {"limits_proposed_active": 39_714_684, "limits_proposed_scope": 33_155_684, "over_new_n": 290,
                "over_new_positive_n": 130, "over_new_zero_n": 160, "approval_n": 421, "behaviour_bonus_n": 0,
                "behaviour_malus_n": 0, "behaviour_effect_active": 0}


def _exact(k: dict, expected: dict) -> None:
    for key, v in expected.items():
        if isinstance(v, float) and v >= 1e5 and not float(v).is_integer():
            assert round(k[key] / 1e6, 2) == round(v / 1e6, 2), (key, k[key], v)
        else:
            assert abs(k[key] - v) < 0.5, (key, k[key], v)


def test_regression_v31_default():
    """v3.1 reference: age bands off and no minimum of invoices (``params.V31``) reproduce the v3.1 numbers
    exactly, with and without the customer master MD105; the old v3 stays reachable with OLD_V3."""
    d = _data()
    if d is None:
        print("  (skipped: data files not found)")
        return
    assert Params().m1_days_basis == "contractual" and Params().behaviour_enabled
    assert _data_no_md105() is not None and _data_no_md105().md105 is None and d.md105 is not None
    _exact(kpis(simulate(_data_no_md105(), Params(**V31_PARAMS))), V31)
    r = simulate(d, Params(**V31_PARAMS))
    _exact(kpis(r), V31)
    assert (r["days_source"].isin(["contractual", "fallback"])).all() and not r["days_capped"].any()
    assert (r["proposed_limit"] % 1 == 0).all()
    capped = r[r["ceiling"].notna()]
    assert (capped["proposed_limit"] <= capped["ceiling_unit"]).all()      # the Cerved ceiling stays hard
    assert (r.loc[r["is_special"], "proposed_limit"] == 0).all()           # special classes stay 0
    old = simulate(d, Params(**OLD_V3))
    _exact(kpis(old), OLD_V3_EXACT)


def _data_no_md105():
    """The real files without the customer master MD105 (ages from the first AR124 invoice)."""
    if "d3" not in _DATA:
        from core.loaders import load_files
        files = [f for f in (ROOT / "data").glob("*.xls*") if "md105" not in f.name.lower()]
        _DATA["d3"] = load_files(files) if len(files) >= 3 else None
    return _DATA["d3"]


V32_MD105 = {  # v3.2 default (decision of 21/11/2026) with MD105: age from the account opening date
    "n_active": 2116, "n_scope": 1598, "limits_proposed_active": 40_562_858, "limits_proposed_scope": 33_601_858,
    "over_new_n": 277, "over_new_positive_n": 117, "over_new_zero_n": 160, "excess_new": 7_035_582.56,
    "higher_n": 803, "lower_n": 618, "equal_n": 177, "approval_n": 426, "zero_with_turnover_n_active": 166,
    "age_new_n": 49, "age_young_n": 205, "age_consolidated_n": 1344, "age_no_history_n": 0,
    "behaviour_bonus_n": 729, "behaviour_tolerance_n": 221, "behaviour_malus_n": 385, "behaviour_no_history_n": 55,
    "behaviour_new_n": 49, "behaviour_few_n": 159, "behaviour_effect_active": 423_000, "behaviour_effect_scope": 348_000,
    "over_current_n": 267, "over_current_positive_n": 202,
}
V32_NO_MD105 = {  # v3.2 default without MD105 (12-month AR124: ages from the first invoice, coverage warning)
    "limits_proposed_active": 41_011_825, "limits_proposed_scope": 33_923_825, "over_new_n": 275,
    "over_new_positive_n": 115, "over_new_zero_n": 160, "approval_n": 428,
    "age_new_n": 78, "age_young_n": 327, "age_consolidated_n": 1138, "age_no_history_n": 55,
    "behaviour_new_n": 78, "behaviour_few_n": 135,
}


def test_regression_v32_default():
    """v3.2 default numbers on the real files, with MD105 (and without it); per band v3.1 vs v3.2."""
    from core.engine import age_findings, coverage_finding
    from core.kpi import age_breakdown
    d = _data()
    if d is None:
        print("  (skipped: data files not found)")
        return
    r = simulate(d, Params())
    _exact(kpis(r), V32_MD105)
    s = r[r["in_scope"]]
    assert s["opened_date"].notna().all()                                 # every customer in scope is in MD105
    assert int(s["age_source"].eq("ar124_earlier").sum()) == 81           # re-created codes: earlier invoice used
    assert coverage_finding(d, Params()) is None                          # MD105 loaded: no coverage warning
    f = {x.code: x for x in age_findings(r, d, Params())}
    assert f["AGE_INVOICE_BEFORE_OPENING"].details["scope_n"] == 81 and "MD_CUSTOMER_MISSING" not in f
    assert (r["months_active"] <= 12).all() and (r["months_active"] >= 1).all()
    assert (r["proposed_limit"] % 1 == 0).all()
    capped = r[r["ceiling"].notna()]
    assert (capped["proposed_limit"] <= capped["ceiling_unit"]).all()      # the Cerved ceiling stays hard
    assert (r.loc[r["is_special"], "proposed_limit"] == 0).all()           # special classes stay 0
    assert (r.loc[r["age_band"].eq("NEW"), "behaviour_pct"] == 0).all()
    ab = age_breakdown(r).set_index("age_band")
    assert list(ab["n"]) == [49, 205, 1344, 0]
    assert list(ab["limits_proposed"]) == [448_000, 2_329_747, 30_824_111, 0]
    assert list(ab["over_new_positive_n"]) == [2, 14, 101, 0]
    # left-censoring: 62 of the 81 re-created codes have their first invoice in the first 31 days of AR124
    assert int(s["age_censored"].sum()) == 62 and (s.loc[s["age_censored"], "age_band"] == "CONSOLIDATED").all()
    assert s.loc[s["age_censored"], "age_source"].eq("ar124_earlier").all()
    # consolidated customers keep exactly the v3.1 rule for the revenue (turnover / 12)
    cons = s["age_band"].eq("CONSOLIDATED")
    assert (s.loc[cons, "months_active"] == 12).all()
    d3 = _data_no_md105()
    r3 = simulate(d3, Params())
    _exact(kpis(r3), V32_NO_MD105)
    s3 = r3[r3["in_scope"]]
    assert int(s3["age_censored"].sum()) == 1138 and set(s3.loc[s3["age_censored"], "age_band"]) == {"CONSOLIDATED"}
    cf = coverage_finding(d3, Params())
    assert cf is not None and cf.code == "AR_SHORT_HISTORY" and cf.details["months"] == 12 and cf.details["needed"] == 18
    assert coverage_finding(d3, Params(age_bands_enabled=False)) is None
