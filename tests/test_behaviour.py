"""v3.1: payment-behaviour bonus / malus and the days basis of the need M1 (SPEC 4).

Synthetic customers: turnover 1.200.000 (100.000 a month), contractual terms 30 days, Cerved
"Affidabile" with no suggested limit unless stated: M1 on terms = 100.000 x 30/30 x 1,1 = 110.000,
base = 220.000, risk factor 1. The delay is set through the closing date of one invoice.
"""
from __future__ import annotations

import io
import json
import math

import numpy as np
import openpyxl
import pandas as pd

from core import texts as T
from core import explain as X
from core.engine import behaviour_pct, simulate
from core.export import BEHAVIOUR_COLUMNS, to_excel
from core.kpi import kpis
from core.params import OLD_V3, V31, Params
from core.sensitivity import sensitivity
from tests.helpers import REF, ar_row, cf_row, close, cv_row, make_data, one
from ui import logic as LG
from ui import scenarios as SC

P = Params(reference_date=REF, **V31)   # v3.1 rules (no age bands): these tests pin the bonus / malus itself


def _cust(code: str, delay: int | None, t12: float = 1_200_000, limit: float = 0, fido=None, risk="E00",
          score="AFFIDABILE", **cf):
    """Customer + Cerved row + one invoice (terms 30, paid ``delay`` days after the due date)."""
    cfr = cf_row(code=code, t12=t12, limit=limit, risk=risk, **cf)
    cvr = cv_row(code=float(code), score=score, fido=fido)
    ar = []
    if delay is not None:
        inv = pd.Timestamp("2026-06-01")
        ar = [ar_row(int(code), inv, inv + pd.Timedelta(days=30), 1000.0, inv + pd.Timedelta(days=30 + delay))]
    return cfr, cvr, ar


def _data(*custs):
    cf, cv, ar = [], [], []
    for a, b, c in custs:
        cf.append(a)
        cv.append(b)
        ar += c
    return make_data(cf, cv, ar or [ar_row(999999, "2026-06-01", "2026-07-01", 1.0, "2026-07-01")])


def test_band_boundaries_with_defaults():
    p = Params()
    d = np.array([-10, 0, 5, 6, 17.5, 30, 60, np.nan])
    pct, band = behaviour_pct(d, p)
    exp = [0.05, 0.05, 0.0, -0.004, -0.05, -0.10, -0.10, 0.0]
    assert np.allclose(pct, exp), pct
    assert list(band) == ["BONUS", "BONUS", "TOLERANCE", "MALUS", "MALUS", "MALUS", "MALUS", "NONE"]
    off, band_off = behaviour_pct(d, Params(behaviour_enabled=False))
    assert (off == 0).all() and set(band_off) == {"NONE"}
    # zero tolerance: any delay > 0 is a malus
    pct0, _ = behaviour_pct(np.array([0.0, 1.0, 10.0]), Params(behaviour_tolerance_days=0, behaviour_full_malus_days=10))
    assert np.allclose(pct0, [0.05, -0.01, -0.10])


def test_engine_bands_on_invoices():
    custs = [_cust(str(i + 1), dl) for i, dl in enumerate([-10, 0, 5, 6, 30, 60])]
    r = simulate(_data(*custs), P)
    exp = {"1": (0.05, 231000), "2": (0.05, 231000), "3": (0.0, 220000), "4": (-0.004, 220000),
           "5": (-0.10, 198000), "6": (-0.10, 198000)}
    for code, (pct, lim) in exp.items():
        x = one(r, code)
        assert x.days_terms == 30 and x.days_used == 30 and x.days_source == "contractual"
        close(x.delay_days, x.days_measured - 30)
        close(x.behaviour_pct, pct)
        close(x.limit_after_behaviour, 220000 * (1 + pct))
        assert x.proposed_limit == lim, (code, x.proposed_limit)
    x = one(r, "4")     # -0,4%: 219.120 rounded up to 220.000 -> no effect, reason stays the formula
    assert x.behaviour_effect == 0 and x.reason_code == X.R_FULL_NEED
    assert one(r, "1").reason_code == X.R_BEHAVIOUR_BONUS and one(r, "5").reason_code == X.R_BEHAVIOUR_MALUS
    assert one(r, "1").behaviour_effect == 11000 and one(r, "5").behaviour_effect == -22000


def test_no_ar_customer_gets_nothing():
    c = _cust("7", None)
    r = simulate(_data(c), P)
    x = one(r, "7")
    assert math.isnan(x.delay_days) and x.behaviour_pct == 0 and x.behaviour_band == "NONE"
    assert x.days_source == "fallback" and x.days_used == 30 and x.proposed_limit == 220000
    rows = LG.step_rows(x, P, "en")
    assert rows[6]["calc"] == T.T("st_beh_calc_none", "en") and rows[6]["ron"] == "220,000"


def test_cerved_ceiling_stays_hard_and_special_classes_zero():
    r = simulate(_data(_cust("1", -5, fido=225_400.7), _cust("2", -5, risk="S09"), _cust("3", -5, fido=0)), P)
    x = one(r, "1")      # 231.000 with the bonus, ceiling 225.400 -> the ceiling (whole RON)
    assert x.proposed_limit == 225_400 and x.reason_code == X.R_CERVED_CAP and x.ceiling_binds
    assert x.proposed_limit_no_behaviour == 220_000 and x.behaviour_effect == 5_400
    assert one(r, "2").proposed_limit == 0 and one(r, "2").reason_code == X.R_SPECIAL
    assert one(r, "3").proposed_limit == 0 and one(r, "3").reason_code == X.R_CERVED_ZERO


def test_rounding_and_minimum_after_the_malus():
    # turnover 48.000: M1 = 4.000 x 1,1 = 4.400, base 8.800; malus -10% -> 7.920 -> 8.000
    # turnover 24.000: base 4.400; malus -> 3.960 -> rounded 4.000 -> minimum 5.000 (as without the malus)
    r = simulate(_data(_cust("1", 60, t12=48_000), _cust("2", 60, t12=24_000), _cust("3", -1, t12=24_000)), P)
    a, b, c = one(r, "1"), one(r, "2"), one(r, "3")
    close(a.limit_after_behaviour, 7920)
    assert a.limit_rounded == 8000 and a.proposed_limit == 8000 and a.proposed_limit_no_behaviour == 9000
    assert a.reason_code == X.R_BEHAVIOUR_MALUS
    assert b.proposed_limit == 5000 and b.reason_code == X.R_MINIMUM and b.behaviour_effect == 0
    close(c.limit_after_behaviour, 4620)   # bonus: 4.620 -> rounded 5.000, as without it: no effect
    assert c.proposed_limit == 5000 and c.behaviour_effect == 0 and c.reason_code == X.R_FULL_NEED


def test_change_codes_where_behaviour_is_decisive():
    r = simulate(_data(_cust("1", -3, limit=225_000), _cust("2", 40, limit=210_000),
                       _cust("3", 40, limit=300_000)), P)
    x = one(r, "1")      # 220.000 without, 231.000 with the bonus; today 225.000
    assert x.direction == "HIGHER" and x.change_code == X.C_HIGHER_BONUS
    y = one(r, "2")      # 220.000 without, 198.000 with the malus; today 210.000
    assert y.direction == "LOWER" and y.change_code == X.C_LOWER_MALUS
    z = one(r, "3")      # lower anyway: the usual sentence, with the formula after the malus
    assert z.change_code == X.C_LOWER_NEED
    for lang in ("it", "en"):
        v = LG.text_values(x, P)
        s1, s2 = T.t(T.CHANGE_TEXTS, x.change_code, lang, **v), T.t(T.CHANGE_TEXTS, y.change_code, lang, **v)
        assert "220" in s1 and "231" in s1 and "225" in s1 and "{" not in s1 + s2
        assert ("+5%" in s1) and ("−3" in s1)
        s3 = T.t(T.CHANGE_TEXTS, y.change_code, lang, **LG.text_values(y, P))
        assert "−10%" in s3 and "+40" in s3 and "198" in s3
        r1 = T.t(T.REASON_LONG_TEXTS, x.reason_code, lang, **LG.text_values(x, P))
        assert "220.000" in r1 or "220,000" in r1


def test_m1_days_basis():
    # measured 90 days, terms 30: measured basis -> min(90, 30 + 15) = 45; contractual -> 30
    c = _cust("1", 60)
    d = _data(c, _cust("2", None))
    meas = one(simulate(d, P.replace(m1_days_basis="measured", behaviour_enabled=False)), "1")
    cont = one(simulate(d, P.replace(behaviour_enabled=False)), "1")
    assert meas.days_used == 45 and meas.days_capped and meas.days_source == "measured"
    assert cont.days_used == 30 and not cont.days_capped and cont.days_source == "contractual"
    assert meas.proposed_limit == 330_000 and cont.proposed_limit == 220_000
    # with the malus the late payer on measured days still gets more than on terms (the Lab help says so)
    both = one(simulate(d, P.replace(m1_days_basis="measured")), "1")
    assert both.proposed_limit == 297_000 > one(simulate(d, P), "1").proposed_limit == 198_000
    # short terms: minimum 15 days; no invoices: fallback days
    short = make_data([cf_row(code="5", t12=1_200_000)], [cv_row(code=5.0)],
                      [ar_row(5, "2026-06-01", "2026-06-11", 100.0, "2026-06-11")])
    s = one(simulate(short, P), "5")
    assert s.days_raw == 10 and s.days_used == 15 and s.days_min_applied
    nf = one(simulate(d, P.replace(fallback_days=45)), "2")
    assert nf.days_source == "fallback" and nf.days_used == 45
    rows = LG.step_rows(cont, P, "en")
    assert rows[2]["calc"].startswith("contractual terms 30 days")


def test_validation_json_roundtrip_and_old_scenarios(tmp=None):
    assert Params(behaviour_bonus_max=0.6).validate() and Params(behaviour_malus_max=-0.01).validate()
    assert Params(behaviour_tolerance_days=-1).validate()
    assert Params(behaviour_full_malus_days=5).validate()          # must be > tolerance (5)
    assert Params(m1_days_basis="actual").validate()
    assert not Params(behaviour_bonus_max=0.5, behaviour_malus_max=0.0, behaviour_tolerance_days=0,
                      behaviour_full_malus_days=1).validate()
    p = Params(behaviour_enabled=False, behaviour_bonus_max=0.07, behaviour_malus_max=0.2,
               behaviour_tolerance_days=10, behaviour_full_malus_days=45, m1_days_basis="measured")
    q = Params.from_json(p.to_json())
    assert q == p and q.to_json() == p.to_json()
    # an old scenario file (before v3.1) has none of the new keys: it loads with the defaults
    old = {k: v for k, v in Params(multiplier=2.5).to_dict().items()
           if not k.startswith("behaviour_") and k != "m1_days_basis"}
    name, loaded, ignored = SC.parse(json.dumps({"name": "Old", "params": old}).encode())
    assert name == "Old" and not ignored and loaded.multiplier == 2.5
    assert loaded.behaviour_enabled and loaded.m1_days_basis == "contractual" and loaded.behaviour_bonus_max == 0.05
    assert Params(**OLD_V3).replace(**OLD_V3) == Params(**OLD_V3)


def test_steps_add_up():
    d = _data(_cust("1", -3, fido=225_400.7), _cust("2", 40), _cust("3", 2), _cust("4", None))
    for p in (P, P.replace(m1_days_basis="measured")):
        r = simulate(d, p)
        for _, row in r.iterrows():
            st = {s["step"]: s for s in X.steps(row, p)}
            beh = next(k for k in st if k.startswith("S_BEHAVIOUR_"))
            close(st[beh]["amount"], st["S_COEF"]["amount"] * (1 + row["behaviour_pct"]))
            ceil = next(k for k in st if k.startswith("S_CEILING") or k == "S_NO_CEILING")
            close(st[ceil]["amount"], min(st[beh]["amount"], row["ceiling_unit"] if pd.notna(row["ceiling"])
                                          else math.inf))
            assert st["S_PROPOSED"]["amount"] == row["proposed_limit"]
            for lang in ("it", "en"):
                rows = LG.step_rows(row, p, lang)
                assert len(rows) == 12 and rows[6]["n"] == "7" and rows[7]["n"] == "8"
                close(rows[6]["amount"], rows[5]["amount"] * (1 + row["behaviour_pct"]))
                assert rows[-1]["amount"] == row["proposed_limit"]
                for t in X.steps_text(X.steps(row, p), lang):
                    assert "{" not in t["calc"] + t["label"], t


def test_kpis_export_sensitivity_and_rules():
    d = _data(_cust("1", -3), _cust("2", 40), _cust("3", 2), _cust("4", None))
    r = simulate(d, P)
    k = kpis(r)
    assert (k["behaviour_bonus_n"], k["behaviour_tolerance_n"], k["behaviour_malus_n"],
            k["behaviour_no_history_n"]) == (1, 1, 1, 1)
    assert k["behaviour_effect_active"] == 11000 - 22000 == float(r["behaviour_effect"].sum())
    ko = kpis(simulate(d, P.replace(behaviour_enabled=False)))
    assert ko["behaviour_bonus_n"] == ko["behaviour_malus_n"] == 0 and ko["behaviour_effect_active"] == 0
    for lang in ("it", "en"):
        wb = openpyxl.load_workbook(io.BytesIO(to_excel(r, P, lang)))
        head = [c.value for c in wb.worksheets[0][1]]
        li = 0 if lang == "it" else 1
        for c in BEHAVIOUR_COLUMNS:
            assert T.COLUMN_TEXTS[c][li] in head, c
        rows = [{h: c.value for h, c in zip(head, row)} for row in wb.worksheets[0].iter_rows(min_row=2)]
        bands = {x[T.COLUMN_TEXTS["code"][li]]: x[T.COLUMN_TEXTS["behaviour_band"][li]] for x in rows}
        assert bands["1"] == T.BAND_TEXTS["BONUS"][lang] and bands["4"] == T.BAND_TEXTS["NONE"][lang]
        wb2 = openpyxl.load_workbook(io.BytesIO(to_excel(simulate(d, Params(**OLD_V3)), Params(**OLD_V3), lang)))
        head2 = [c.value for c in wb2.worksheets[0][1]]
        assert T.COLUMN_TEXTS["behaviour_pct"][li] not in head2
    for key, vals in (("behaviour_bonus_max", [0.0, 0.05, 0.1]), ("behaviour_malus_max", [0.0, 0.2]),
                      ("behaviour_tolerance_days", [0, 10]), ("behaviour_full_malus_days", [10, 60])):
        s = sensitivity(d, P, key, vals, kpi_keys=["limits_proposed_active", "behaviour_effect_active"])
        assert list(s["value"]) == vals
    s = sensitivity(d, P, "behaviour_bonus_max", [0.0, 0.1], kpi_keys=["behaviour_effect_active"])
    assert s["behaviour_effect_active"].iloc[1] > s["behaviour_effect_active"].iloc[0]
    for lang in ("it", "en"):
        sec = LG.rules(P, 10, lang)
        txt = LG.rules_text(sec, lang)
        assert T.T("rl_beh_formula", lang) in txt and "5%" in txt and "10%" in txt and "30" in txt
        assert "{" not in txt
        old = LG.rules_text(LG.rules(Params(**OLD_V3), 10, lang), lang)
        assert T.T("rl_behaviour_off", lang).replace("**", "") in old
        assert T.T("rl_beh_formula", lang) not in old
