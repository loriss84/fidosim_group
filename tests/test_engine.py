"""Formula rules on small synthetic data. Base case: T12 120.000, 30 days -> M1 11.000."""
import math

from core.engine import simulate
from core import explain as X
from core.params import Params, OLD_V3
from tests.helpers import REF, close, cf_row, cv_row, make_data, one

P = Params(reference_date=REF, **OLD_V3)  # unit tests of the v3 mechanics (v3.1: see test_behaviour)


def run(cf, cv=None, p=P, **kw):
    return simulate(make_data(cf, cv if cv is not None else [], None), p, **kw)


def test_m1_multiplier_buffer():
    r = run([cf_row(code="1", t12=120000)], [cv_row(code=1.0, score="AFFIDABILE")])
    x = one(r, "1")
    close(x.m1, 11000)
    close(x.base_limit, 22000)
    assert x.proposed_limit == 22000 and x.reason_code == X.R_FULL_NEED
    x = one(run([cf_row(code="1", t12=120000)], [cv_row(code=1.0)], P.replace(multiplier=1.5, buffer=0)), "1")
    close(x.base_limit, 15000)


def test_coefficients():
    cf = [cf_row(code=str(i), t12=1200000) for i in range(1, 6)]
    cv = [cv_row(code=1.0, score="AFFIDABILE"), cv_row(code=2.0, score="CAUTELA"),
          cv_row(code=3.0, score="MASSIMA CAUTELA"), cv_row(code=4.0, score=None)]
    r = run(cf, cv)
    assert [one(r, c).coefficient for c in "12345"] == [1.0, 0.7, 0.0, 0.5, 0.5]
    assert one(r, "2").proposed_limit == 154000 and one(r, "2").reason_code == X.R_COEF_CAUTION
    assert one(r, "3").proposed_limit == 0 and one(r, "3").reason_code == X.R_MAX_CAUTION
    assert one(r, "4").score_bucket == "NONE" and one(r, "4").in_cerved     # in Cerved, no score
    assert one(r, "5").reason_code == X.R_COEF_NOT_IN_CERVED
    r = run(cf, cv, P.replace(coef_caution=0.5, coef_not_in_cerved=0.0))
    assert one(r, "2").coefficient == 0.5 and one(r, "5").reason_code == X.R_ZERO_COEF


def test_exempt_not_in_cerved_coefficient():
    cf = [cf_row(code="1", t12=1200000, risk="EKM"), cf_row(code="2", t12=1200000)]
    r = run(cf, [], P.replace(coef_exempt_not_in_cerved=1.0))
    assert one(r, "1").coefficient == 1.0 and one(r, "2").coefficient == 0.5
    assert one(r, "1").is_exempt and not one(r, "1").in_scope


def test_cerved_ceiling_ron_eur_zero_disabled():
    cf = [cf_row(code=str(i), t12=1200000) for i in range(1, 5)]
    cv = [cv_row(code=1.0, fido=50000.4), cv_row(code=2.0, fido=10000, cur="EUR"),
          cv_row(code=3.0, fido=0), cv_row(code=4.0, fido=None)]
    r = run(cf, cv, P.replace(ceiling_is_hard=False))
    assert one(r, "1").ceiling_binds and one(r, "1").proposed_limit == 51000   # rounded up (legacy)
    assert one(r, "1").reason_code == X.R_CERVED_CAP
    close(one(r, "2").ceiling, 49750)
    assert one(r, "2").proposed_limit == 50000
    assert one(r, "3").proposed_limit == 0 and one(r, "3").reason_code == X.R_CERVED_ZERO
    assert math.isnan(one(r, "4").ceiling) and one(r, "4").proposed_limit == 220000
    r = run(cf, cv, P.replace(eur_ron=5.0))
    close(one(r, "2").ceiling, 50000)
    r = run(cf, cv, P.replace(cerved_cap_enabled=False))
    assert all(one(r, c).proposed_limit == 220000 for c in "1234")


def test_hard_ceiling():
    """Rule 8 (lead decision): final = min(rounded limit with minimum, Cerved ceiling itself)."""
    cf = [cf_row(code=str(i), t12=t) for i, t in
          enumerate([1200000, 1200000, 1200000, 1200000, 12000, 24688, 24688], 1)]
    cv = [cv_row(code=1.0, fido=50000.4),     # rounding up would give 51.000 -> ceiling in whole RON 50.000
          cv_row(code=2.0, fido=3400),        # minimum 5.000 never above the ceiling -> 3.400
          cv_row(code=3.0, fido=800),         # ceiling below the step -> 800 (not floored to 0)
          cv_row(code=4.0, fido=0),           # 0 stays 0
          cv_row(code=5.0, fido=4200),        # need 2.200 -> 3.000 -> min 5.000 -> ceiling 4.200
          cv_row(code=6.0, fido=4583),        # need 4.526 -> 5.000 -> ceiling 4.583 (not 4.000)
          cv_row(code=7.0, fido=None)]        # no ceiling: 4.526 -> 5.000
    r = run(cf, cv)                           # default ceiling_is_hard=True
    exp = {"1": 50000, "2": 3400, "3": 800, "4": 0, "5": 4200, "6": 4583, "7": 5000}
    for c, v in exp.items():
        close(one(r, c).proposed_limit, v)
    assert round(one(r, "6").limit_after_coef) == 4526
    for c in "123456":
        assert one(r, c).proposed_limit <= one(r, c).ceiling
        assert one(r, c).reason_code == (X.R_CERVED_ZERO if c == "4" else X.R_CERVED_CAP), c
    # the ceiling in whole RON (50.000) already applies at step 4, so rounding has nothing to cut
    assert one(r, "1").ceiling_binds and one(r, "1").limit_after_ceiling == 50000
    assert not one(r, "1").hard_cap_applied
    assert not one(r, "2").min_applied and one(r, "5").hard_cap_applied and not one(r, "5").ceiling_binds
    assert one(r, "7").reason_code == X.R_FULL_NEED and not one(r, "7").hard_cap_applied
    soft = run(cf, cv, P.replace(ceiling_is_hard=False))
    assert [one(soft, c).proposed_limit for c in "12345"] == [51000, 5000, 5000, 0, 5000]
    assert one(soft, "2").reason_code == X.R_MINIMUM_OVER_CAP
    # step-by-step and customer page show the ceiling itself
    e = X.explain_customer(r, "6", P)
    hard = next(s for s in e["steps"] if s["step"] == "S_HARD_CAP")
    assert hard["amount"] == 4583 and hard["values"]["ceiling"] == 4583


def test_hard_ceiling_whole_ron():
    """Limits held at the Cerved ceiling are whole RON: floor(ceiling) (4.582,72 -> 4.582)."""
    from core import texts as T
    cf = [cf_row(code=str(i), t12=t) for i, t in enumerate([24688, 12000, 1200000, 1200000], 1)]
    cv = [cv_row(code=1.0, fido=4582.72), cv_row(code=2.0, fido=867.14),
          cv_row(code=3.0, fido=10000, cur="EUR"),          # 49.750 RON (float noise must not lose 1 RON)
          cv_row(code=4.0, fido=12345.999)]
    r = run(cf, cv)
    assert [one(r, c).proposed_limit for c in "1234"] == [4582, 867, 49750, 12345]
    assert all(float(one(r, c).proposed_limit).is_integer() for c in "1234")
    assert all(one(r, c).reason_code == X.R_CERVED_CAP for c in "1234")
    for c in "1234":
        assert one(r, c).ceiling_unit == one(r, c).proposed_limit
    for lang, want in (("it", "4.582"), ("en", "4,582")):
        v = X.text_values(one(r, "1"), P)
        assert want in T.t(T.REASON_LONG_TEXTS, X.R_CERVED_CAP, lang, **v)
        rows = X.steps_text(X.explain_customer(r, "1", P)["steps"], lang)
        hard = next(x for x in rows if x["step"] == "S_HARD_CAP")
        assert hard["calc"].endswith(("4.582 (RON interi)", "4,582 (whole RON)")) and hard["amount"] == 4582
    soft = run(cf, cv, P.replace(ceiling_is_hard=False))
    assert one(soft, "1").proposed_limit == 5000            # legacy: rounding up and minimum


def test_full_need_reason_not_reliable_when_not_in_cerved():
    from core import texts as T
    cf = [cf_row(code="1", t12=1200000), cf_row(code="2", t12=1200000), cf_row(code="3", t12=1200000)]
    cv = [cv_row(code=2.0, score="AFFIDABILE"), cv_row(code=3.0, score=None)]
    r = run(cf, cv, P.replace(coef_not_in_cerved=1.0))
    assert one(r, "1").coefficient == 1 and one(r, "1").reason_code == X.R_FULL_NEED_NEUTRAL
    assert one(r, "3").reason_code == X.R_FULL_NEED_NEUTRAL       # in Cerved without score
    assert one(r, "2").reason_code == X.R_FULL_NEED
    for lang in ("it", "en"):
        v = X.text_values(one(r, "1"), P)
        txt = T.t(T.REASON_TEXTS, X.R_FULL_NEED_NEUTRAL, lang, **v)
        assert "affidabile" not in txt.lower() and "reliable" not in txt.lower(), txt
    r = run(cf, cv, P.replace(coef_caution=1.0))
    assert one(run([cf_row(code="9", t12=1200000)], [cv_row(code=9.0, score="CAUTELA")],
                   P.replace(coef_caution=1.0)), "9").reason_code == X.R_FULL_NEED_NEUTRAL


def test_cerved_currency_and_negative_limit():
    cf = [cf_row(code=str(i), t12=1200000) for i in range(1, 5)]
    cv = [cv_row(code=1.0, fido=10000, cur="USD"), cv_row(code=2.0, fido=-2000),
          cv_row(code=3.0, fido=10000, cur=None), cv_row(code=4.0, fido=10000, cur="eur")]
    d = make_data(cf, cv)
    f = {x.code: x for x in d.findings}
    assert f["CV_OTHER_CURRENCY"].count == 1 and f["CV_OTHER_CURRENCY"].details["currencies"] == "USD"
    assert f["CV_NEGATIVE_LIMIT"].count == 1
    assert f["CV_NO_CURRENCY"].count == 1 and f["CV_NO_CURRENCY"].details["assumed"] == "RON"
    r = simulate(d, P)
    assert math.isnan(one(r, "1").ceiling) and one(r, "1").proposed_limit == 220000   # no cap, never RON
    assert math.isnan(one(r, "2").ceiling) and one(r, "2").proposed_limit == 220000   # invalid: no cap
    assert one(r, "2").reason_code == X.R_FULL_NEED
    assert one(r, "3").ceiling == 10000                                                # blank = RON
    close(one(r, "4").ceiling, 49750)
    steps = [s["step"] for s in X.explain_customer(r, "1", P)["steps"]]
    assert "S_CEILING_INVALID" in steps


def test_special_exempt_intercompany_scope():
    cf = [cf_row(code="1", t12=1200000, risk="S09", balance=10),
          cf_row(code="2", t12=1200000, risk="EKM", balance=10 ** 7),
          cf_row(code="30001069", t12=1200000, balance=10 ** 7),
          cf_row(code="4", t12=0, balance=0),            # inactive
          cf_row(code="5", t12=-50, balance=100)]        # active, negative turnover
    r = run(cf)
    assert set(r.code) == {"1", "2", "5"}
    s = one(r, "1")
    assert s.proposed_limit == 0 and s.reason_code == X.R_SPECIAL and not s.in_scope and not s.over_new
    e = one(r, "2")
    assert e.proposed_limit > 0 and not e.over_new and not e.over_current      # exempt: never over
    n = one(r, "5")
    assert n.proposed_limit == 0 and n.m1 == 0 and n.reason_code == X.R_NO_TURNOVER and n.over_new
    full = run(cf, include_all=True)
    ic = one(full, "30001069")
    assert ic.is_intercompany and ic.reason_code == X.R_INTERCOMPANY and ic.change_code == X.C_EXCLUDED
    r = run(cf, p=P.replace(intercompany_codes=[]))
    assert "30001069" in set(r.code)


def test_rounding_and_minimum():
    cf = [cf_row(code="1", t12=130000), cf_row(code="2", t12=12000), cf_row(code="3", t12=600)]
    cv = [cv_row(code=1.0), cv_row(code=2.0), cv_row(code=3.0)]
    r = run(cf, cv)            # base 23.833,3 / 2.200 / 110
    assert one(r, "1").proposed_limit == 24000
    assert one(r, "2").proposed_limit == 5000 and one(r, "2").min_applied
    assert one(r, "2").reason_code == X.R_MINIMUM
    r = run(cf, cv, P.replace(rounding_mode="down"))
    assert one(r, "1").proposed_limit == 23000
    assert one(r, "2").proposed_limit == 5000           # 2.000 -> minimum
    assert one(r, "3").proposed_limit == 0 and one(r, "3").reason_code == X.R_ROUNDED_ZERO
    r = run(cf, cv, P.replace(rounding_step=500, min_limit=0))
    assert one(r, "1").proposed_limit == 24000 and one(r, "2").proposed_limit == 2500


def test_exposure_over_limit_flags():
    cf = [cf_row(code="1", t12=120000, balance=20000, ordered=1000, delivered=2000, limit=30000)]
    x = one(run(cf, [cv_row(code=1.0)]), "1")
    assert x.exposure == 23000 and x.proposed_limit == 22000
    assert x.over_new and not x.over_current and x.excess_new == 1000 and x.excess_current == 0


def test_plausibility():
    cf = [cf_row(code="1", t12=120000), cf_row(code="2", t12=120000), cf_row(code="3", t12=120000)]
    cv = [cv_row(code=1.0, fatt=1_000_000), cv_row(code=2.0, fatt=1_500_000), cv_row(code=3.0, fatt=0)]
    r = run(cf, cv)
    close(one(r, "1").plausibility_ratio, 0.12)
    assert one(r, "1").plausibility_flag and not one(r, "2").plausibility_flag
    assert not one(r, "3").plausibility_flag and math.isnan(one(r, "3").plausibility_ratio)
    r = run(cf, cv, P.replace(plausibility_threshold=0.2))
    assert not one(r, "1").plausibility_flag


def test_approval_and_tier():
    cf = [cf_row(code="1", t12=120000, limit=20000),    # 22.000 vs 20.000: +10%
          cf_row(code="2", t12=120000, limit=10000),    # +120%
          cf_row(code="3", t12=120000, limit=0),        # new limit
          cf_row(code="4", t12=120000, limit=22000),    # equal
          cf_row(code="5", t12=12_000_000, limit=0)]    # 2.200.000 RON ~ 442k EUR -> tier 3
    cv = [cv_row(code=float(i)) for i in range(1, 6)]
    r = run(cf, cv)
    assert [bool(one(r, c).approval_needed) for c in "1234"] == [False, True, True, False]
    assert one(r, "4").direction == "EQUAL" and one(r, "4").change_code == X.C_EQUAL
    assert one(r, "3").change_code == X.C_HIGHER_NO_CURRENT
    assert one(r, "2").change_code == X.C_HIGHER_NEED
    assert one(r, "1").tier == 1 and one(r, "5").tier == 3
    r = run(cf, cv, P.replace(approval_threshold=0.05, tier2_eur=500000))
    assert not one(r, "1").approval_needed and one(r, "5").tier == 2   # +2.000 RON: below materiality
    r = run(cf, cv, P.replace(approval_threshold=0.05, approval_min_change_ron=0))
    assert one(r, "1").approval_needed


def test_approval_materiality():
    """Approval only when |change| > threshold % AND |change| > approval_min_change_ron (5.000)."""
    cf = [cf_row(code="1", t12=12000, limit=1000),      # 1.000 -> 5.000: +400% but +4.000 RON
          cf_row(code="2", t12=120000, limit=0),       # 0 -> 22.000: new limit above 5.000
          cf_row(code="3", t12=12000, limit=0),        # 0 -> 5.000: exactly 5.000, not above
          cf_row(code="4", t12=1200000, limit=300000),  # 220.000 vs 300.000: -26.7%, -80.000
          cf_row(code="5", t12=1200000, limit=230000)]  # 220.000 vs 230.000: -4.3%
    cv = [cv_row(code=float(i)) for i in range(1, 6)]
    r = run(cf, cv)
    assert [bool(one(r, c).approval_needed) for c in "12345"] == [False, True, False, True, False]
    r = run(cf, cv, P.replace(approval_min_change_ron=0))
    assert [bool(one(r, c).approval_needed) for c in "12345"] == [True, True, True, True, False]
    assert Params().approval_min_change_ron == 5000


def test_reason_priority_and_change_codes():
    # special beats no turnover; no turnover beats Cerved zero; cap beats minimum
    cf = [cf_row(code="1", t12=0, balance=5, risk="S09"),
          cf_row(code="2", t12=0, balance=5),
          cf_row(code="3", t12=1200000, limit=500000),
          cf_row(code="4", t12=1200000, limit=500000),
          cf_row(code="5", t12=1200000, limit=500000)]
    cv = [cv_row(code=1.0, fido=0), cv_row(code=2.0, fido=0), cv_row(code=3.0, fido=0),
          cv_row(code=4.0, fido=10000, score="CAUTELA"), cv_row(code=5.0, fido=None)]
    r = run(cf, cv)
    assert [one(r, c).reason_code for c in "12345"] == [
        X.R_SPECIAL, X.R_NO_TURNOVER, X.R_CERVED_ZERO, X.R_CERVED_CAP, X.R_FULL_NEED]
    assert [one(r, c).change_code for c in "345"] == [X.C_LOWER_CERVED_ZERO, X.C_LOWER_CERVED_CAP,
                                                      X.C_LOWER_NEED]


def test_steps_and_texts():
    from core import texts as T
    p = P
    r = run([cf_row(code="1", t12=1200000, limit=100000)], [cv_row(code=1.0, fido=50000.4, score="CAUTELA")])
    e = X.explain_customer(r, "1", p)
    keys = [s["step"] for s in e["steps"]]
    assert keys[0] == "S_TURNOVER" and "S_CEILING_BINDS" in keys
    ceil = next(s for s in e["steps"] if s["step"] == "S_CEILING_BINDS")
    assert ceil["amount"] == 50000 and ceil["values"]["ceiling"] == 50000   # whole RON, not 50.000,4
    assert e["steps"][-2]["amount"] == 50000
    for lang in ("it", "en"):
        rows = X.steps_text(e["steps"], lang)
        assert all(isinstance(x["calc"], str) for x in rows)
        assert "50" in T.t(T.REASON_LONG_TEXTS, e["reason_code"], lang, **e["values"])
    assert T.t(T.REASON_TEXTS, "R_MINIMUM", "it", min_limit=5000) == "Minimo 5.000 RON"
    assert T.t(T.REASON_TEXTS, "R_MINIMUM", "en", min_limit=5000) == "Minimum 5,000 RON"
    # every code has IT and EN text
    for table, codes in ((T.REASON_TEXTS, X.REASON_CODES), (T.CHANGE_TEXTS, X.CHANGE_CODES)):
        for c in codes:
            assert set(table[c]) == {"it", "en"}, c
