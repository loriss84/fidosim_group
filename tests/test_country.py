"""Multi-country version: profiles, local currency, Slovakia without Cerved, RÚZ balance sheets,
manual balance sheets, and the Romanian results unchanged (golden snapshot)."""
from __future__ import annotations

import gzip
import json
import os
import re
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from core import balance as BS
from core import bs_providers as BP
from core import country as CO
from core import texts as TX
from core.engine import simulate
from core.loaders import load_files, normalize_vat
from core.params import Params
from tests import golden, synthetic

FIX = Path(__file__).parent / "fixtures"
WEBSUPPORT_DIC = "2021869234"   # Websupport s. r. o., a real Slovak company (RÚZ data are CC0)


@contextmanager
def country(code: str):
    old = CO.active().code
    CO.set_active(code)
    try:
        yield CO.active()
    finally:
        CO.set_active(old)


def _ruz_fixture() -> dict:
    with gzip.open(FIX / "ruz_responses.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


def _fake_ruz(rec: dict, calls: list[str] | None = None):
    """RÚZ answers recorded for Websupport; any DIČ / IČO is answered with Websupport."""
    q = next(u for u in rec if "uctovne-jednotky?" in u)

    def fetch(url: str, timeout: float):
        if calls is not None:
            calls.append(url)
        if "uctovne-jednotky?" in url:
            return rec[q]
        return rec[url]
    return fetch


# --- profiles and parameters -------------------------------------------------------------------
def test_profiles_and_country_defaults():
    assert set(CO.CODES) == {"RO", "SK", "AT", "CZ", "DE", "HU"}
    ro, sk = Params(), Params.for_country("SK")
    assert ro.country == "RO" and ro.min_limit == 5000 and ro.eur_rate == 4.975
    assert ro.intercompany_codes == ["30001069", "30005389", "30001070"]
    assert Params.for_country("RO") == ro                 # Romania's defaults are the old defaults
    assert (sk.country, sk.min_limit, sk.rounding_step, sk.approval_min_change, sk.eur_rate) == ("SK", 1000, 250, 1000, 1.0)
    assert sk.intercompany_codes == [] and sk.multiplier == ro.multiplier and sk.coef_caution == ro.coef_caution
    cz, hu = Params.for_country("CZ"), Params.for_country("HU")
    assert (cz.min_limit, cz.rounding_step, hu.min_limit, hu.rounding_step) == (25000, 5000, 400000, 100000)
    assert not sk.validate() and not cz.validate() and not hu.validate()
    assert any("country" in e for e in Params(country="XX").validate())
    assert Params(country="sk").country == "SK"
    # scenario files of the single-country simulator (old parameter names) load as they are
    old = json.loads(ro.to_json())
    old["eur_ron"], old["approval_min_change_ron"] = 5.0, 7000
    del old["eur_rate"], old["approval_min_change"], old["country"]
    p = Params.from_dict(old)
    assert (p.eur_rate, p.approval_min_change, p.country) == (5.0, 7000, "RO")


def test_formula_changes_ignore_local_defaults():
    from ui import logic as LG
    sk = Params.for_country("SK")
    assert LG.formula_changes(sk, "it")[0] == 0                       # local values are not "changes"
    assert LG.base_params(sk.replace(multiplier=2.5)) == sk
    assert LG.formula_changes(sk.replace(min_limit=2000), "en")[0] == 1


def test_currency_in_texts_follows_the_country():
    tpl = TX.REASON_TEXTS["R_MINIMUM"]["it"]
    with country("SK"):
        out = TX.render(tpl, "it", min_limit=1000)
        assert "EUR" in out and "RON" not in out
        assert TX.T("p_eur_rate", "en") == "Exchange rate (EUR per 1 EUR)"
        assert "RÚZ" in TX.T("cust_tab_balance", "it")
    with country("HU"):
        assert "HUF" in TX.render(tpl, "en", min_limit=400000)
        assert "e-beszámoló" in TX.T("cust_tab_balance", "en")
        assert "Romania" not in TX.T("blk_caption", "it", terms=30, d=5, ref="x")
    assert "RON" in TX.render(tpl, "it", min_limit=5000)
    assert "ANAF" in TX.T("cust_tab_balance", "it")
    assert "In Romania" in TX.T("blk_caption", "it")


def test_country_texts_complete():
    """Every country override has both languages and the placeholders of the text it replaces."""
    ph = lambda s: sorted(set(re.findall(r"\{(\w+)\}", s)))  # noqa: E731
    for code, d in TX.COUNTRY_TEXTS.items():
        for k, v in d.items():
            assert k in TX.TEXTS, (code, k)
            assert v["it"] and v["en"], (code, k)
            assert ph(v["it"]) == ph(v["en"]), (code, k)
            assert set(ph(v["it"])) <= set(ph(TX.TEXTS[k]["it"])), (code, k)      # no value the page lacks
            assert "ANAF" not in v["it"] + v["en"] and "rumen" not in v["it"], (code, k)
    for code in ("AT", "CZ", "DE", "HU"):
        assert TX.COUNTRY_TEXTS[code]["blk_caption"]["it"] != TX.TEXTS["blk_caption"]["it"], code


def test_vat_prefix_and_detection():
    CO.set_active("RO")
    with country("SK"):
        assert normalize_vat("SK 2021869234") == "2021869234"
        assert normalize_vat("RO 14697790") == "RO14697790"     # foreign for Slovakia
    assert normalize_vat("RO 14697790") == "14697790"
    with country("SK"):
        d = load_files(synthetic.files("SK"))
    assert CO.detect(d.checkfidi) == "SK"
    assert CO.detect(load_files(synthetic.files("RO")).checkfidi) == "RO"


# --- Romania: identical to the single-country simulator ----------------------------------------
def test_golden_romania_unchanged():
    CO.set_active("RO")
    """Results, sentences, tables, steps, rules, quality checks and Excel of the synthetic Romanian data
    are identical to fidosim_romania 30d71e7 (the snapshot was written with that code)."""
    diffs = golden.compare(golden.load(), golden.as_golden(golden.snapshot()))
    assert not diffs, "\n".join(diffs)


# --- Slovakia without Cerved ------------------------------------------------------------------
def test_slovakia_without_cerved():
    warnings.filterwarnings("ignore")
    p = Params.for_country("SK")
    with country("SK"):
        d = load_files(synthetic.files("SK"))
        assert d.missing == ["cerved"] and d.ok
        r = simulate(d, p)
    assert len(r) > 300
    assert set(r["score_bucket"]) == {"NONE"} and not r["in_cerved"].any()
    formula = r["reason_code"].isin(["R_COEF_NOT_IN_CERVED", "R_BEHAVIOUR_BONUS", "R_BEHAVIOUR_MALUS",
                                     "R_NEW_CUSTOMER", "R_YOUNG_CUSTOMER"])
    assert np.allclose(r.loc[formula, "coefficient"], 0.5)
    pos = r["proposed_limit"] > 0
    assert (r.loc[pos, "proposed_limit"] >= 1000).all()                    # local minimum (EUR)
    assert ((r.loc[pos, "proposed_limit"] % 250) == 0).all()               # local rounding (EUR)
    assert r["ceiling"].isna().all()                                        # no Cerved, no ceiling
    assert "R_MINIMUM" in set(r["reason_code"]) and "R_CERVED_CAP" not in set(r["reason_code"])
    # the same files read as Romania would keep the "SK" prefix: the country matters for matching only
    assert simulate(d, p.replace(min_limit=5000))["proposed_limit"].max() >= 5000


# --- RÚZ (Slovakia) -----------------------------------------------------------------------------
def test_ruz_key_from_vat():
    pr = BP.for_country("SK")
    assert pr.automatic and pr.source == "ruz"
    assert pr.key_from("SK2021869234") == ("2021869234", "ok")             # IČ DPH
    assert pr.key_from(None, "36421928") == ("36421928", "ok")             # IČO
    assert pr.key_from("SK 364219") == ("00364219", "ok")                  # IČO without leading zeros
    assert pr.key_from("CZ27082440") == (None, "foreign")
    assert pr.key_from(None, "") == (None, "missing")


def test_ruz_parser_pod_and_micro_templates():
    rec = _ruz_fixture()
    # micro entity (template "Úč MUJ"): figures checked against the report on registeruz.sk
    v, raw = BP.parse_ruz_report(rec["MUJ_REPORT"], rec["MUJ_TEMPLATE"])
    assert v["equity"] == 13442 and v["share_capital"] == 6000 and v["debts"] == 5244
    assert v["turnover"] == 14766 and v["net_profit"] == 7879 and v["current_assets"] == 18686
    assert raw[0][:2] == ["A1", "SPOLU MAJETOK r. 02 + r. 14"]
    # full lookup of a company with the "Úč POD" template, recorded answers
    calls: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        res = BP.for_country("SK").lookup(WEBSUPPORT_DIC, cache_dir=tmp, refresh=True, fetch=_fake_ruz(rec, calls))
        assert res["status"] == "ok" and res["name"].startswith("Websupport")
        assert (res["year"], res["period_end_month"], res["template"]) == (2025, 12, "Úč POD")
        v = res["values"]
        assert v["equity"] == 3558912 and v["turnover"] == 13148139 and v["net_profit"] == 991807
        assert v["debts"] == 4155968 - 199379                                # provisions out, as ANAF
        assert res["report_url"].startswith("https://www.registeruz.sk/cruz-public/domain/financialreport/show/")
        n = len(calls)
        again = BP.for_country("SK").cached(WEBSUPPORT_DIC, tmp)            # saved on this PC
        assert again["status"] == "ok" and again["from_cache"] and len(calls) == n
        a = BS.assess(v, res["year"], 100000, 50000, 200000, bp=BS.BalanceParams(round_to=250),
                      period_end_month=res["period_end_month"])
        assert a.verdict == "valid" and a.capacity == 355750                  # 10% of equity, rounded to 250


def test_ruz_errors_and_no_data():
    def down(url, timeout):
        raise OSError("connection refused")
    res = BP.for_country("SK").lookup("12345678", fetch=down)
    assert res["status"] == "error" and "refused" in res["error"]

    def nothing(url, timeout):
        return {"id": [], "existujeDalsieId": False}
    assert BP.for_country("SK").lookup("12345678", fetch=nothing)["status"] == "not_found"

    def pdf_only(url, timeout):                                              # IFRS company: only a PDF
        if "uctovne-jednotky?" in url:
            return {"id": [1]}
        if "uctovna-jednotka?" in url:
            return {"id": 1, "nazovUJ": "BIG a.s.", "idUctovnychZavierok": [10]}
        if "uctovna-zavierka?" in url:
            return {"id": 10, "obdobieOd": "2025-01", "obdobieDo": "2025-12", "typ": "Riadna", "idUctovnychVykazov": [7]}
        return {"id": 7, "idSablony": 709, "pristupnostDat": "Verejné prílohy", "prilohy": [{"id": 1}]}
    res = BP.for_country("SK").lookup("12345678", fetch=pdf_only, today=__import__("datetime").date(2026, 11, 24))
    assert res["status"] == "no_data" and res["newer_pdf"]["period"] == "2025-12"


def test_assess_uses_the_fiscal_year_end():
    v = {"equity": 100000.0, "debts": 10000.0, "current_assets": 50000.0}
    d = __import__("datetime").date(2026, 11, 24)
    assert BS.assess(v, 2025, 1000, 0, today=d).age_months == 11
    assert BS.assess(v, 2025, 1000, 0, today=d, period_end_month=6).age_months == 17


# --- manual balance sheets (AT, CZ, DE, HU) ---------------------------------------------------
def test_manual_providers():
    for code in ("AT", "CZ", "DE", "HU"):
        pr = BP.for_country(code)
        assert not pr.automatic and pr.source == "manual"
        assert pr.search_url("x").startswith("https://")
    assert BP.for_country("HU").key_from("HU12345678-2-42") == ("12345678", "ok")
    assert BP.for_country("CZ").key_from("CZ27082440") == ("27082440", "ok")
    assert BP.for_country("CZ").search_url("27082440").endswith("ico=27082440")
    assert BP.for_country("AT").key_from("ATU12345678") == ("U12345678", "ok")
    assert BP.for_country("DE").key_from("ATU12345678") == (None, "foreign")
    pr = BP.for_country("AT")
    with tempfile.TemporaryDirectory() as tmp:
        assert pr.cached("U12345678", tmp) is None
        res = pr.save("U12345678", {"equity": 500000.0, "debts": 2e6, "current_assets": 3e5,
                                    "turnover": 4e6, "net_result": -20000.0, "share_capital": None}, 2025, tmp, "X GmbH")
        assert res["values"]["net_loss"] == 20000 and "share_capital" not in res["values"]
        back = pr.cached("U12345678", tmp)
        assert back["status"] == "ok" and back["entered"]["equity"] == 500000
        a = BS.assess(back["values"], back["year"], 30000, 0, bp=BS.BalanceParams(round_to=250))
        assert a.verdict == "too_high" and set(a.weaknesses) == {"loss", "leverage", "liquidity"} and a.capacity == 25000
        pr.delete("U12345678", tmp)
        assert pr.cached("U12345678", tmp) is None


# --- pages: Slovakia end to end ----------------------------------------------------------------
@contextmanager
def _env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update(kv)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_pages_slovakia_without_cerved():
    """Slovak files (no Cerved): the country is recognised, every page works in both languages, no RON
    anywhere, and the Customer page reads the RÚZ balance sheet."""
    from streamlit.testing.v1 import AppTest
    from tests.test_app import APP, TIMEOUT, check_texts, visible_strings, watch
    rec = _ruz_fixture()
    real = BP._ruz_get
    calls: list[str] = []
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as ws:
        synthetic.write(data_dir, "SK")
        BP._ruz_get = _fake_ruz(rec, calls)
        BP._templates.clear()
        try:
            with _env(FIDO_DATA_DIR=data_dir, FIDO_WORKSPACE_DIR=ws), watch():
                for lang in ("EN", "IT"):
                    lg = lang.lower()
                    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
                    at.run()
                    assert not at.exception, [e.value for e in at.exception]
                    if lang != "EN":
                        at.segmented_control(key="lang_seg").set_value(lang).run()
                    assert at.session_state["params"].country == "SK"
                    assert at.session_state["params"].min_limit == 1000
                    for page in ("data", "results", "customer", "lab", "rules"):
                        at.switch_page(f"ui/pages/{page}.py").run()
                        assert not at.exception, (page, [e.value for e in at.exception])
                        strings = visible_strings(at)
                        bad = [s for s in strings if re.search(r"\bRON\b", s)]
                        assert not bad, (page, bad[:3])
                        check_texts(at, lang, f"SK {page}")
                    at.switch_page("ui/pages/data.py").run()
                    md = " ".join(m.value for m in at.markdown)
                    assert TX.T("data_country_detected", lg, country=CO.get("SK").name(lg), cur="EUR") in \
                        " ".join(x.value for x in at.info)
                    assert "EUR" in md
                    # Customer page: biggest customer with a VAT number, read RÚZ (recorded answers)
                    at.switch_page("ui/pages/customer.py").run()
                    btn = next(b for b in at.button if str(b.key).startswith("bs_btn_"))
                    btn.click().run()
                    assert not at.exception, [e.value for e in at.exception]
                    text = " ".join(x.value for x in list(at.markdown) + list(at.caption))
                    assert "Websupport" in text and "RÚZ" in text, text[:500]
                    assert TX.T("bs_read_title", lg) in text
                    assert any(f.startswith("ruz_SK_") for f in os.listdir(Path(ws) / "bilanci"))
        finally:
            BP._ruz_get = real
    assert calls


def test_pages_country_switch_and_manual_balance():
    """Switching to Austria on the Data page: local values change, the formula stays; the Customer page
    offers the register link and the manual form, and the typed figures give the second opinion."""
    from streamlit.testing.v1 import AppTest
    from tests.test_app import APP, TIMEOUT, watch
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as ws:
        synthetic.write(data_dir, "SK")
        with _env(FIDO_DATA_DIR=data_dir, FIDO_WORKSPACE_DIR=ws), watch():
            at = AppTest.from_file(APP, default_timeout=TIMEOUT)
            at.run()
            at.switch_page("ui/pages/data.py").run()
            at.selectbox(key="w_country_pick").set_value("AT").run()
            assert not at.exception, [e.value for e in at.exception]
            p = at.session_state["params"]
            assert p.country == "AT" and p.min_limit == 1000 and p.multiplier == 2.0
            warn = " ".join(w.value for w in at.warning)
            assert TX.T("data_country_mismatch", "en", detected="Slovakia", country="Austria") in warn
            cf = synthetic.build("SK")["checkfidi"]
            no_vat = cf[cf["VAT"].isna() & (cf["Turnover 12 months"] > 0)]["Code"].iloc[0]
            at.session_state["customer"] = no_vat          # no VAT: typed in by hand, keyed by customer code
            at.switch_page("ui/pages/customer.py").run()
            assert not at.exception, [e.value for e in at.exception]
            assert any("Firmenbuch" in str(b.proto) for b in at.get("link_button"))
            eq = next(n for n in at.number_input if str(n.key).endswith("_equity"))
            eq.set_value(400000.0)
            next(n for n in at.number_input if str(n.key).endswith("_debts")).set_value(100000.0)
            next(n for n in at.number_input if str(n.key).endswith("_current_assets")).set_value(150000.0)
            next(b for b in at.button if "Save" in str(b.label)).click().run()
            assert not at.exception, [e.value for e in at.exception]
            text = " ".join(x.value for x in list(at.markdown) + list(at.caption))
            assert TX.T("bs_read_title", "en") in text
            assert any(f.startswith("manual_AT_") for f in os.listdir(Path(ws) / "bilanci"))
            # back to the country of the file
            at.switch_page("ui/pages/data.py").run()
            at.selectbox(key="w_country_pick").set_value("SK").run()
            assert at.session_state["params"].country == "SK" and not at.exception
