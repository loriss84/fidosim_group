"""Parameters: defaults, validation, JSON round trip."""
from core.params import PARAM_META, Params


def test_defaults_v3():
    p = Params()
    assert (p.multiplier, p.buffer, p.min_days, p.cap_extra_days, p.fallback_days) == (2.0, 0.10, 15, 15, 30)
    assert (p.coef_reliable, p.coef_caution, p.coef_max_caution, p.coef_not_in_cerved) == (1.0, 0.7, 0.0, 0.5)
    assert (p.rounding_step, p.rounding_mode, p.min_limit, p.eur_rate) == (1000, "up", 5000.0, 4.975)
    assert (p.plausibility_threshold, p.approval_threshold, p.tier1_eur, p.tier2_eur) == (0.10, 0.20, 50000, 200000)
    assert p.ceiling_is_hard and p.cerved_cap_enabled
    assert p.intercompany_codes == ["30001069", "30005389", "30001070"]
    assert p.validate() == []


def test_json_round_trip():
    p = Params(multiplier=2.5, rounding_mode="down", reference_date="2026-10-01",
               intercompany_codes=["1", "2"], ceiling_is_hard=False)
    q = Params.from_json(p.to_json())
    assert q == p and q.to_dict() == p.to_dict()
    assert Params.from_dict({"multiplier": "3", "unknown": 1}).multiplier == 3.0
    assert p.diff(Params()) and set(p.diff(Params())) >= {"multiplier", "rounding_mode"}


def test_validation():
    assert Params(multiplier=-1).validate()
    assert Params(rounding_mode="sideways").validate()
    assert Params(tier1_eur=300000).validate()           # tier2 < tier1
    assert Params(reference_date="not a date").validate()
    try:
        Params(buffer=5).check()
    except ValueError as e:
        assert "buffer" in str(e)
    else:
        raise AssertionError
    for k, m in PARAM_META.items():
        assert m["group"] in ("need", "risk", "behaviour", "age", "caps", "controls", "populations"), k
    # 15 of v3.1 + the 4 customer-age parameters (user decision, 21/11/2026)
    assert sum(m["primary"] for m in PARAM_META.values()) <= 19
    assert Params(new_customer_months=13).validate()                     # new > consolidated (12)
    assert Params(behaviour_min_invoices=-1).validate() and Params(consolidated_months=0).validate()
