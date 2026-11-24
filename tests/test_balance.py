"""Public balance sheet (ANAF): parsing, CUI, lookup with fake answers, assessment, Customer page.

No network: ANAF answers are simulated. Real answers (Nov 2026) for 2025 were used to pick the values.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

from core import balance as BS
from core import texts as TX

# Real ANAF 2025 answer for SPOT SERV SRL (CUI 36979652), descriptions as published (with diacritics)
SPOT = [("I1", 213890, "ACTIVE IMOBILIZATE - TOTAL"), ("I2", 342286, "ACTIVE CIRCULANTE - TOTAL, din care:"),
        ("I3", 97879, "Stocuri"), ("I4", 185519, "Creante"), ("I5", 58888, "Casa şi conturi la bănci"),
        ("I6", 0, "CHELTUIELI IN AVANS"), ("I7", 688954, "DATORII"), ("I8", 0, "VENITURI IN AVANS"),
        ("I9", 0, "PROVIZIOANE"), ("I10", -132778, "CAPITALURI - TOTAL, din care:"),
        ("I11", 200, "Capital subscris varsat"), ("I12", 0, "Patrimoniul regiei"),
        ("I13", 959356, "Cifra de afaceri neta"), ("I14", 960549, "VENITURI TOTALE"),
        ("I15", 1083950, "CHELTUIELI TOTALE"), ("I16", 0, "Profit brut"), ("I17", 123401, "Pierdere bruta"),
        ("I18", 0, "Profit net"), ("I19", 132998, "Pierdere  neta"), ("I20", 4, "Numar mediu de salariati")]


def _answer(rows, year=2025, cui=36979652, name="SPOT SERV SRL"):
    return {"an": year, "cui": cui, "deni": name, "caen": 4612, "den_caen": "Intermedieri",
            "i": [{"indicator": c, "val_indicator": v, "val_den_indicator": d} for c, v, d in rows]}


def _empty(year, cui):
    return {"an": year, "cui": cui, "deni": "", "caen": 0, "den_caen": "", "i": []}


def test_parse_by_description_not_code():
    v = BS.parse_indicators(_answer(SPOT)["i"])
    assert v["equity"] == -132778 and v["turnover"] == 959356 and v["debts"] == 688954
    assert v["net_loss"] == 132998 and v["net_profit"] == 0 and v["cash"] == 58888
    assert v["share_capital"] == 200 and v["employees"] == 4
    # 'VENITURI IN AVANS' must not be read as total revenue
    assert v["total_revenue"] == 960549
    # same descriptions under other codes -> same result
    shuffled = [(f"X{i}", val, d) for i, (_, val, d) in enumerate(reversed(SPOT))]
    assert BS.parse_indicators(_answer(shuffled)["i"]) == v


def test_cui_from_vat():
    assert BS.cui_from_vat("RO 15117182") == ("15117182", "ok")
    assert BS.cui_from_vat("13165477") == ("13165477", "ok")
    assert BS.cui_from_vat(float("nan"), "RO 4323209") == ("4323209", "ok")
    assert BS.cui_from_vat("HU12345678") == (None, "foreign")
    assert BS.cui_from_vat(None, "") == (None, "missing")


def test_lookup_goes_back_years_and_caches():
    calls = []

    def fake(url, timeout):
        calls.append(url)
        return _empty(2025, 1) if "an=2025" in url else _answer(SPOT, 2024)

    with tempfile.TemporaryDirectory() as d:
        r = BS.lookup("36979652", today=date(2026, 3, 1), cache_dir=Path(d), fetch=fake)
        assert r["status"] == "ok" and r["year"] == 2024 and r["years_tried"] == [2025, 2024]
        assert r["url"].endswith("an=2024&cui=36979652") and not r["from_cache"]
        r2 = BS.lookup("36979652", today=date(2026, 3, 1), cache_dir=Path(d), fetch=fake)
        assert r2["from_cache"] and len(calls) == 2 and r2["values"] == r["values"]
        BS.lookup("36979652", today=date(2026, 3, 1), cache_dir=Path(d), fetch=fake, refresh=True)
        assert len(calls) == 4


def test_lookup_not_found_and_error_not_cached():
    with tempfile.TemporaryDirectory() as d:
        r = BS.lookup("4323209", today=date(2026, 11, 21), cache_dir=Path(d), fetch=lambda u, t: _empty(0, 0))
        assert r["status"] == "not_found" and r["years_tried"] == [2025, 2024, 2023]

        def boom(url, timeout):
            raise OSError("no route")
        e = BS.lookup("1", today=date(2026, 11, 21), cache_dir=Path(d), fetch=boom)
        assert e["status"] == "error" and "no route" in e["error"]
        assert not (Path(d) / "anaf_1.json").exists() or BS.lookup(
            "1", today=date(2026, 11, 21), cache_dir=Path(d), fetch=lambda u, t: _answer(SPOT))["status"] == "ok"


def _vals(**kw):
    base = {"equity": 1_000_000, "turnover": 5_000_000, "debts": 1_000_000, "current_assets": 1_500_000,
            "net_profit": 100_000, "net_loss": 0}
    base.update(kw)
    return base


def test_assess_rules():
    t = date(2026, 11, 21)
    # healthy: room = 10% of equity
    a = BS.assess(_vals(), 2025, 50_000, 30_000, today=t)
    assert (a.verdict, a.capacity, a.suggested, a.share_used) == ("valid", 100_000, 50_000, 0.10)
    assert abs(a.ratios["limit_on_equity"] - 0.05) < 1e-9 and not a.weaknesses
    # too high -> the correct limit is the capacity
    h = BS.assess(_vals(), 2025, 150_000, 0, today=t)
    assert (h.verdict, h.suggested) == ("too_high", 100_000)
    # a weakness halves the room: loss, heavy debts, low liquidity
    for kw, w in ((dict(net_profit=0, net_loss=1), "loss"),
                  (dict(debts=4_000_000, current_assets=5_000_000), "leverage"),
                  (dict(current_assets=500_000), "liquidity")):
        x = BS.assess(_vals(**kw), 2025, 50_000, 0, today=t)
        assert (x.verdict, x.capacity, x.weaknesses) == ("valid_watch", 50_000, [w]), (kw, x)
        y = BS.assess(_vals(**kw), 2025, 60_000, 0, today=t)
        assert (y.verdict, y.suggested) == ("too_high", 50_000), kw
    # rounding down to 1,000
    assert BS.assess(_vals(equity=325_279, debts=2_261_702, current_assets=2_062_984), 2025, 26_790, 0,
                     today=t).suggested == 16_000           # SC Atmosferica 2025
    # old balance sheet: still valid, to watch
    old = BS.assess(_vals(), 2023, 50_000, 0, today=t)
    assert old.verdict == "valid_watch" and old.old and old.age_months == 35
    # negative equity
    neg = BS.assess(_vals(equity=-1), 2025, 50_000, 0, today=t)
    assert (neg.verdict, neg.capacity, neg.suggested) == ("too_high", 0, 0)
    assert BS.assess(_vals(equity=-1), 2025, 0, 87_000, today=t).verdict == "zero_confirmed"
    z = BS.assess(_vals(), 2025, 0, 0, today=t)
    assert (z.verdict, z.capacity) == ("zero_formula", 100_000)
    assert BS.assess({"turnover": 1}, 2025, 5_000, 0, today=t).verdict == "na"
    # thresholds are parameters
    assert BS.assess(_vals(), 2025, 150_000, 0, today=t, bp=BS.BalanceParams(equity_share=0.2)).verdict == "valid"


def test_every_verdict_and_reading_has_texts():
    keys = [f"bs_v_{v}" for v in BS.VERDICTS] + [f"bs_vs_{v}" for v in BS.VERDICTS] + [
        "bs_v_too_high_zero", "bs_why_capacity", "bs_why_weak", "bs_why_neg", "bs_weak_loss", "bs_weak_leverage",
        "bs_weak_liquidity", "bs_old", "bs_q_size", "bs_q_profit", "bs_q_equity", "bs_q_debt", "bs_q_liq",
        "bs_q_siad", "bs_rules", "bs_tech", "cust_tab_calc", "cust_tab_profile", "cust_tab_balance",
        "cust_tab_invoices", "cust_badge_bs"]
    for k in keys:
        for lg in ("it", "en"):
            assert TX.T(k, lg) != k and TX.TEXTS[k][lg], (k, lg)


def test_customer_page_button_with_fake_anaf():
    from tests.test_app import go, new_app, watch
    real = BS._http_get
    calls = []

    def fake(url, timeout):
        calls.append(url)
        return _answer(SPOT)
    old_ws = os.environ.get("FIDO_WORKSPACE_DIR")
    with tempfile.TemporaryDirectory() as d:
        os.environ["FIDO_WORKSPACE_DIR"] = d
        BS._http_get = fake
        try:
            with watch():
                for lang in ("EN", "IT"):
                    lg = lang.lower()
                    at = go(new_app(lang), "customer")
                    at.session_state["customer"] = "30006222"      # SPOT SERV: max caution, limit 0
                    go(at, "customer")
                    btn = next(b for b in at.button if b.key == "bs_btn_36979652")
                    btn.click().run()
                    assert not at.exception, [e.value for e in at.exception]
                    ok = " ".join(x.value for x in at.success)
                    assert TX.T("bs_v_zero_confirmed", lg) in ok, ok
                    assert TX.T("bs_why_neg", lg).split("(")[0] in ok
                    badges = " ".join(x.value for x in at.markdown)
                    assert TX.T("cust_badge_bs", lg, year=2025, v=TX.T("bs_vs_zero_confirmed", lg)) in badges
                    md = " ".join(x.value for x in at.markdown)
                    assert TX.T("bs_box_values", lg) in md and TX.T("bs_box_ratios", lg) in md
                    assert TX.T("bs_q_equity", lg) in md and TX.T("bs_read_title", lg) in md
                    assert (Path(d) / "anaf" / "anaf_36979652.json").exists()
            assert len(calls) == 2   # one click per language, cached in between is refreshed on click
        finally:
            BS._http_get = real
            if old_ws is None:
                os.environ.pop("FIDO_WORKSPACE_DIR", None)
            else:
                os.environ["FIDO_WORKSPACE_DIR"] = old_ws
