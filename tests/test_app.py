"""UI tests with streamlit.testing.v1.AppTest on the real files in data/.

Every page in IT and EN, language switch, Lab parameters vs core KPIs, sensitivity, scenarios
(save / compare / load / export / import / delete), Customer page for every kind of customer,
Excel download, start with data/ empty or partial, uploads, no deprecation warnings and no
untranslated strings. Run with ``python -m tests.run_all`` (or this module's ``main``).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402
import streamlit.testing.v1.app_test as _apptest_mod  # noqa: E402

from core import texts as TX  # noqa: E402
from core.engine import simulate  # noqa: E402
from core.explain import REASON_CODES, CHANGE_CODES  # noqa: E402
from core.kpi import kpis  # noqa: E402
from core.loaders import load_folder  # noqa: E402
from core.params import OLD_V3, Params  # noqa: E402
from core.sensitivity import sensitivity  # noqa: E402
from ui import logic as LG  # noqa: E402
from ui import scenarios as SC  # noqa: E402

APP = str(ROOT / "app.py")
# The app starts empty by default; the tests load the real files from data/ through FIDO_DATA_DIR.
os.environ.setdefault("FIDO_DATA_DIR", str(ROOT / "data"))
DATA = ROOT / "data"
PAGES = ["data", "results", "customer", "lab", "rules"]
TIMEOUT = 120

# --- capture download-button payloads (AppTest makes a new in-memory store each run) ---
_STORES: list[MemoryMediaFileStorage] = []


class _CapturingStorage(MemoryMediaFileStorage):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        _STORES.append(self)


_apptest_mod.MemoryMediaFileStorage = _CapturingStorage


def download_bytes(button) -> bytes:
    name = button.proto.url.rsplit("/", 1)[-1]
    for s in reversed(_STORES):
        try:
            return s.get_file(name).content
        except Exception:
            continue
    raise AssertionError(f"download payload {name} not found")


# --- log / warning capture ---------------------------------------------------
class _Grab(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records: list[str] = []

    def emit(self, rec):
        self.records.append(rec.getMessage())


@contextmanager
def watch():
    """Collect Python warnings and Streamlit log warnings; fail on deprecations."""
    h = _Grab()
    loggers = [logging.getLogger(n) for n in list(logging.root.manager.loggerDict) if n.startswith("streamlit")]
    loggers.append(logging.getLogger("streamlit"))
    for lg in loggers:
        lg.addHandler(h)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            yield h
        finally:
            for lg in loggers:
                lg.removeHandler(h)
    msgs = h.records + [str(x.message) for x in w]
    bad = [m for m in msgs if re.search(r"deprecat|will be removed|use_container_width", m, re.I)]
    assert not bad, "deprecation warnings: " + " | ".join(bad[:5])
    noisy = [m for m in h.records if "ScriptRunContext" not in m and "Session state does not function" not in m]
    assert not noisy, "Streamlit warnings: " + " | ".join(noisy[:5])


# --- shared fixtures ---------------------------------------------------------
_CORE: dict = {}


def core_data():
    if "d" not in _CORE:
        _CORE["d"] = load_folder(DATA)
    return _CORE["d"]


def expected(p: Params | None = None) -> dict:
    return kpis(simulate(core_data(), p or Params()))


@contextmanager
def env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update({k: str(v) for k, v in kv.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def new_app(lang: str = "EN") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    if lang != "EN":
        at.segmented_control(key="lang_seg").set_value(lang).run()
    return at


def go(at: AppTest, page: str) -> AppTest:
    at.switch_page(f"ui/pages/{page}.py").run()
    assert not at.exception, (page, [e.value for e in at.exception])
    return at


def metrics(at: AppTest) -> dict[str, tuple[str, str]]:
    return {m.label: (m.value, m.delta) for m in at.metric}


FIELD_RE = re.compile(r'^\s*(label|body|help|placeholder|value|options|default|text|caption|title)(?:\[\d+\])?: "(.*)"$',
                      re.M)


def visible_strings(at: AppTest) -> list[str]:
    """Every user-visible string field of the element tree (labels, markdown, help, options...)."""
    out: list[str] = []

    def walk(node):
        proto = getattr(node, "proto", None)
        if proto is not None:
            out.extend(m.group(2) for m in FIELD_RE.finditer(str(proto)))
        for ch in getattr(node, "children", {}).values() if isinstance(getattr(node, "children", None), dict) else []:
            walk(ch)

    walk(at._tree)
    return out


IT_ONLY = re.compile(r"\b(Clienti|clienti|Fido|fido|Più|Esposizione|Calcolo|Regole|Scarica|Ripristina|attuale)\b")
EN_ONLY = re.compile(r"\b(Customers|Exposure|limits?|Download|Reset|Proposed|Current|Change|Rules)\b")
CODE_RE = re.compile(r"^(R|C|S)_[A-Z_]+$")


def check_texts(at: AppTest, lang: str, where: str) -> None:
    strings = visible_strings(at)
    assert strings, where
    keys = set(TX.TEXTS)
    for s in strings:
        s2 = s.encode().decode("unicode_escape") if "\\" in s else s
        assert s2 not in keys or s2 in ("Tier",), f"{where}: untranslated key {s2!r}"
        assert not CODE_RE.match(s2), f"{where}: raw code {s2!r}"
        assert not re.search(r"\{[a-z_]+\}", s2), f"{where}: unfilled placeholder in {s2!r}"
        if lang == "EN":
            m = IT_ONLY.search(s2)
            assert not m, f"{where}: Italian word {m.group(0)!r} in EN text {s2!r}"
        else:
            m = EN_ONLY.search(s2)
            assert not m, f"{where}: English word {m.group(0)!r} in IT text {s2!r}"


# =============================================================================
# Tests
# =============================================================================
def test_texts_complete():
    """Copy deck: both languages, same placeholders; every key used by the UI exists."""
    for k, v in TX.TEXTS.items():
        assert v["it"] and v["en"], k
        ph = lambda s: sorted(set(re.findall(r"\{(\w+)\}", s)))  # noqa: E731
        assert ph(v["it"]) == ph(v["en"]), (k, ph(v["it"]), ph(v["en"]))
    for table, codes in ((TX.REASON_LONG_TEXTS, REASON_CODES), (TX.REASON_TEXTS, REASON_CODES),
                         (TX.CHANGE_TEXTS, CHANGE_CODES)):
        for c in codes:
            assert set(table[c]) == {"it", "en"}, c
    used = set()
    for f in list((ROOT / "ui").rglob("*.py")) + [ROOT / "app.py"]:
        src = f.read_text(encoding="utf-8")
        used |= set(re.findall(r"""(?:\bL|\btl|TX\.T|C\.L)\(\s*["']([a-zA-Z0-9_ ]+)["']""", src))
    missing = sorted(k for k in used if k not in TX.TEXTS and not k.endswith("_"))
    assert not missing, missing
    assert set(TX.PARAM_TEXTS) == set(Params().to_dict())


def test_logic_steps_match_core_for_every_customer():
    d = core_data()
    for p in (Params(), Params(**OLD_V3), Params(rounding_mode="down", min_limit=10000, cerved_cap_enabled=False),
              Params(m1_days_basis="measured", behaviour_bonus_max=0.3, behaviour_malus_max=0.5)):
        res = simulate(d, p)
        for lang in ("it", "en"):
            for _, row in res.iterrows():
                rows = LG.step_rows(row, p, lang)
                assert len(rows) == (12 if p.behaviour_enabled else 11)
                nums = [r["amount"] for r in rows[:-1] if r["amount"] is not None]
                assert abs(nums[-1] - row["proposed_limit"]) < 0.5, (row["code"], nums[-1], row["proposed_limit"])
                assert rows[-1]["amount"] == row["proposed_limit"]


def test_logic_worked_example():
    """UX.md 4.2 worked example (ALFA GAZ SRL) through the fixed step table and sentences."""
    from tests.helpers import ar_row, cf_row, cv_row, make_data
    ar = [ar_row(30012345, "2026-01-10", "2026-03-11", 1000.0, "2026-03-21")]
    d = make_data([cf_row(code="30012345", name="ALFA GAZ SRL", t12=600000, limit=300000, balance=118400,
                          ordered=24000, delivered=20000, risk="B2")],
                  [cv_row(code=30012345.0, score="CAUTELA", fido=150000, fatt=9800000)], ar)
    p = Params(reference_date="2026-11-20", **OLD_V3)   # the UX.md example uses the old v3 formula
    row = simulate(d, p).iloc[0]
    rows = LG.step_rows(row, p, "en")
    assert rows[2]["calc"] == "measured 70 days; minimum 15, maximum terms 60 (at least 15) + 15 = 75 → 70 days"
    assert [r["ron"] for r in rows] == ["600,000", "50,000", "", "128,333", "256,667", "179,667", "150,000",
                                        "150,000", "150,000", "150,000", "150,000"]
    assert rows[6]["calc"] == "Cerved suggests 150,000 → the lower one applies"
    assert LG.reason_long(row, p, "en") == ("The limit is the Cerved suggested limit (150,000 RON): we never go "
                                            "above it, not even with rounding or the 5,000 RON minimum.")
    assert LG.why_change(row, p, "en") == ("Lower: held at the Cerved suggested limit (150,000 RON); the formula "
                                           "gives 179,667 RON; today's limit is 300,000 RON.")
    assert rows[4]["step"] == "Base limit (×2 multiplier)" and rows[5]["step"] == "Risk factor: Caution"
    assert LG.step_rows(row, p, "it")[3]["calc"] == "50.000 × 70 / 30 × (1 + 10%)"


def test_scenarios_store_roundtrip():
    tmp = Path(tempfile.mkdtemp())
    try:
        p = Params(multiplier=2.5)
        SC.save(tmp, "Moltiplicatore 2,5", p)
        assert SC.exists(tmp, "Moltiplicatore 2,5")
        (s,) = SC.list_all(tmp)
        assert s["name"] == "Moltiplicatore 2,5" and s["params"] == p
        name, p2, ign = SC.parse(json.dumps({"name": "X", "params": {"multiplier": 3, "foo": 1}}))
        assert (name, p2.multiplier, ign) == ("X", 3.0, ["foo"])
        for bad in (b"not json", b"[1,2]", b'{"a": 1}', b'{"multiplier": 99}'):
            try:
                SC.parse(bad)
                raise AssertionError(bad)
            except ValueError:
                pass
        SC.delete(tmp, s["file"])
        assert SC.list_all(tmp) == []
    finally:
        shutil.rmtree(tmp)


def test_app_every_page_in_both_languages():
    k = expected()
    with watch():
        for lang in ("EN", "IT"):
            at = new_app(lang)
            for page in PAGES:
                go(at, page)
                check_texts(at, lang, f"{lang}/{page}")
            go(at, "results")
            m = metrics(at)
            lg = lang.lower()
            over = TX.T("kpi_over_n", lg)
            assert m[over][0] == LG.num(k["over_new_n"], lg) == "277"           # v3.2 with MD105 (v3.1: 290)
            assert m[over][1].startswith("+10 ")
            pos = TX.T("kpi_over_pos", lg)                       # headline: over a positive limit
            assert m[pos][0] == LG.num(k["over_new_positive_n"], lg) == "117"  # v3.1: 130
            assert m[pos][1].startswith("-85 ") and "(202)" in m[pos][1]
            split = TX.T("kpi_over_split", lg, z="160", p="117", zc="65", pc="202")
            assert any(c.value == split for c in at.caption), split
            lim = TX.T("kpi_limits", lg, n=LG.num(k["n_active"], lg))
            assert m[lim][0] == LG.big(k["limits_proposed_active"], lg)
            assert m[lim][0] == ("40.56 M RON" if lang == "EN" else "40,56 mln RON")   # v3.1: 39,97
            assert m[lim][1].startswith("+0") and "0" in m[lim][1]
            lims = TX.T("kpi_limits_scope", lg, n=LG.num(k["n_scope"], lg))
            assert m[lims][0] == ("33.60 M RON" if lang == "EN" else "33,60 mln RON")  # v3.1: 33,03
            assert m[lims][1].startswith("+1")       # v3.2: +1,50 M on the scope (v3.1: +0,93 M)
            assert m[TX.T("kpi_approval", lg)][0] == LG.num(k["approval_n"], lg)
            assert at.dataframe, "customer table missing"
            assert len(at.get("download_button")) == 1


def test_language_switch_keeps_numbers():
    with watch():
        at = go(new_app("EN"), "results")
        en = [m.value for m in at.metric]
        at.segmented_control(key="lang_seg").set_value("IT").run()
        assert at.title[0].value == TX.T("res_title", "it")
        it = [m.value for m in at.metric]
        norm = lambda v: re.sub(r"[.,\s]|mln|M", "", v)  # noqa: E731
        assert [norm(x) for x in en] == [norm(x) for x in it]
        at.segmented_control(key="lang_seg").set_value(None).run()  # deselect: language stays
        assert at.title[0].value == TX.T("res_title", "it")


def test_lab_parameters_move_kpis_as_core_says():
    with watch():
        at = go(new_app("EN"), "lab")
        lab = lambda: {m.label.rstrip(" •"): m for m in at.metric}  # noqa: E731

        def check(p: Params) -> None:
            k = expected(p)
            m = lab()
            assert m["Over limit, total"].value == LG.num(k["over_new_n"], "en"), (m["Over limit, total"].value, k["over_new_n"])
            assert m["Over a positive limit"].value == LG.num(k["over_new_positive_n"], "en")
            assert m["Total limits · all active"].value == LG.big(k["limits_proposed_active"], "en")
            assert m["Total limits · scope"].value == LG.big(k["limits_proposed_scope"], "en")
            assert m["Exposure over limit"].value == LG.big(k["excess_new"], "en")
            assert m["Zero limit with turnover"].value == LG.num(k["zero_with_turnover_n_active"], "en")
            assert m["Need approval"].value == LG.num(k["approval_n"], "en")

        check(Params())
        assert all(not m.delta for m in at.metric)
        at.slider(key="w_multiplier").set_value(2.5).run()
        p = Params(multiplier=2.5)
        check(p)
        assert lab()["Total limits · all active"].delta.endswith("vs v3.2")
        assert "Changed: Multiplier (× Need M1) 2.00 → 2.50" in " ".join(c.value for c in at.caption)
        assert any("Formula changed (1 parameters)" in x.value for x in at.sidebar.markdown)
        at.slider(key="w_coef_caution").set_value(0.8).run()
        p = p.replace(coef_caution=0.8)
        check(p)
        at.toggle(key="w_cerved_cap_enabled").set_value(False).run()
        p = p.replace(cerved_cap_enabled=False)
        check(p)
        at.number_input(key="w_min_limit").set_value(10000).run()
        at.segmented_control(key="w_rounding_step").set_value(5000).run()
        at.slider(key="w_buffer").set_value(20).run()
        p = p.replace(min_limit=10000, rounding_step=5000, buffer=0.2)
        check(p)
        assert any(s.label.endswith(" •") for s in at.slider)
        # Effect tab lists the changed customers
        assert any("customers change" in c.value for c in at.caption)
        # Results and Customer follow the Lab scenario, with the banner
        go(at, "results")
        assert any("You are looking at scenario" in i.value for i in at.info)
        assert metrics(at)["Over limit, total"][0] == LG.num(expected(p)["over_new_n"], "en")
        go(at, "rules")
        assert "(changed)" in " ".join(x.value for x in at.markdown)
        # reset from the sidebar
        at.sidebar.button(key="sb_reset").click().run()
        go(at, "lab")
        check(Params())
        assert at.slider(key="w_multiplier").value == 2.0
        assert any(c.value == "No changes: this is the v3.2 formula." for c in at.caption)


def test_lab_payment_behaviour_and_days_basis():
    """v3.1 options in the Lab, IT and EN: switch the bonus/malus off and on, change its values and the
    days basis of M1; KPIs follow the core; no exceptions, warnings or untranslated keys anywhere."""
    with watch():
        for lang in ("EN", "IT"):
            lg = lang.lower()
            at = go(new_app(lang), "lab")
            lab = lambda: {m.label.rstrip(" •"): m for m in at.metric}  # noqa: E731

            def check(p: Params) -> None:
                k = expected(p)
                m = lab()
                assert m[TX.T("lab_kpi_limits", lg)].value == LG.big(k["limits_proposed_active"], lg)
                assert m[TX.T("lab_kpi_over_n", lg)].value == LG.num(k["over_new_n"], lg)
                if p.behaviour_enabled:
                    assert m[TX.T("lab_kpi_bonus", lg)].value == LG.num(k["behaviour_bonus_n"], lg)
                    assert m[TX.T("lab_kpi_malus", lg)].value == LG.num(k["behaviour_malus_n"], lg)
                    assert m[TX.T("lab_kpi_beh_effect", lg)].value == LG.big(k["behaviour_effect_active"], lg)
                    assert at.slider(key="w_behaviour_bonus_max")
                else:
                    assert TX.T("lab_kpi_bonus", lg) not in m
                check_texts(at, lang, f"lab/behaviour/{lang}")

            p = Params()
            check(p)                                   # v3.1 default: on, contractual terms
            assert at.segmented_control(key="w_m1_days_basis").value == "contractual"
            assert at.toggle(key="w_cap_days_enabled").proto.disabled
            at.toggle(key="w_behaviour_enabled").set_value(False).run()
            p = p.replace(behaviour_enabled=False)
            check(p)
            at.toggle(key="w_behaviour_enabled").set_value(True).run()
            p = p.replace(behaviour_enabled=True)
            check(p)
            at.slider(key="w_behaviour_bonus_max").set_value(8).run()
            at.slider(key="w_behaviour_malus_max").set_value(15).run()
            p = p.replace(behaviour_bonus_max=0.08, behaviour_malus_max=0.15)
            check(p)
            at.number_input(key="w_behaviour_tolerance_days").set_value(10).run()
            at.number_input(key="w_behaviour_full_malus_days").set_value(45).run()
            p = p.replace(behaviour_tolerance_days=10, behaviour_full_malus_days=45)
            check(p)
            at.segmented_control(key="w_m1_days_basis").set_value("measured").run()
            p = p.replace(m1_days_basis="measured")
            check(p)
            assert not at.toggle(key="w_cap_days_enabled").proto.disabled
            # sensitivity accepts the new numeric parameters
            at.selectbox(key="sens_key").set_value("behaviour_malus_max").run()
            at.button(key="sens_run").click().run()
            assert not at.exception and at.dataframe
            for page in ("rules", "customer", "results"):
                go(at, page)
                check_texts(at, lang, f"{page}/behaviour/{lang}")
            go(at, "rules")
            md = " ".join(x.value for x in at.markdown)
            assert TX.T("rl_beh_formula", lg) in md and "15%" in md and "45" in md
            at.sidebar.button(key="sb_reset").click().run()
            go(at, "lab")
            check(Params())


def test_lab_sensitivity():
    with watch():
        at = go(new_app("EN"), "lab")
        assert any("Pick a parameter" in i.value for i in at.info)
        at.selectbox(key="sens_key").set_value("multiplier").run()
        at.button(key="sens_run").click().run()
        assert not at.exception
        df = at.session_state["sens"]["df"]
        assert len(df) == 9 and df["value"].tolist()[0] == 1.0 and df["value"].tolist()[-1] == 3.0
        ref = sensitivity(core_data(), Params(), "multiplier", df["value"].tolist(), kpi_keys=["over_new_n"])
        assert df["over_new_n"].tolist() == ref["over_new_n"].tolist()
        assert len(at.get("arrow_vega_lite_chart")) >= 2 or len(at.get("vega_lite_chart")) >= 2
        # parameters change -> result kept but flagged stale
        at.slider(key="w_multiplier").set_value(2.25).run()
        assert any("press Run to update" in c.value for c in at.caption)
        # invalid range
        at.number_input(key="sens_from_multiplier").set_value(3.0).run()
        at.number_input(key="sens_to_multiplier").set_value(1.0).run()
        at.button(key="sens_run").click().run()
        assert any("must be lower" in e.value for e in at.error)
        # an integer parameter
        at.selectbox(key="sens_key").set_value("min_days").run()
        at.button(key="sens_run").click().run()
        assert at.session_state["sens"]["key"] == "min_days" and not at.exception


def test_scenarios_save_compare_export_import():
    tmp = tempfile.mkdtemp()
    try:
        with env(FIDO_WORKSPACE_DIR=tmp), watch():
            at = go(new_app("EN"), "lab")
            assert any("No saved scenarios" in i.value for i in at.info)
            at.button(key="scn_save").click().run()
            assert any("Give the scenario a name" in e.value for e in at.error)
            at.slider(key="w_multiplier").set_value(2.5).run()
            at.text_input(key="scn_name_in").input("Multiplier 2.5").run()
            at.button(key="scn_save").click().run()
            assert (Path(tmp) / "multiplier-2-5.json").exists()
            assert any("Scenario \"Multiplier 2.5\"" in x.value for x in at.sidebar.caption)
            # same name without overwrite -> refused; with overwrite -> ok
            at.slider(key="w_coef_caution").set_value(0.8).run()
            at.button(key="scn_save").click().run()
            assert any("already exists" in e.value for e in at.error)
            at.checkbox(key="scn_over").check().run()
            at.button(key="scn_save").click().run()
            saved = json.loads((Path(tmp) / "multiplier-2-5.json").read_text())
            assert saved["params"]["coef_caution"] == 0.8 and saved["params"]["multiplier"] == 2.5
            # second scenario, then compare
            at.sidebar.button(key="sb_reset").click().run()
            go(at, "lab")
            at.number_input(key="w_min_limit").set_value(10000).run()
            at.text_input(key="scn_name_in").input("Minimum 10000").run()
            at.button(key="scn_save").click().run()
            names = [s["name"] for s in SC.list_all(Path(tmp))]
            assert names == ["Minimum 10000", "Multiplier 2.5"]
            # comparison table: v3, current limits, two saved (KPIs as the core says)
            assert at.selectbox(key="scn_pick").options == ["Minimum 10000", "Multiplier 2.5"]
            # load the first one
            at.selectbox(key="scn_pick").set_value("multiplier-2-5.json").run()
            at.button(key="scn_load").click().run()
            p = Params(multiplier=2.5, coef_caution=0.8)
            assert at.session_state["params"] == p
            assert at.slider(key="w_multiplier").value == 2.5
            assert {m.label.rstrip(" •"): m.value for m in at.metric}["Over limit, total"] == \
                LG.num(expected(p)["over_new_n"], "en")
            # export
            exp = [b for b in at.get("download_button") if b.proto.label == "Export JSON"][0]
            body = json.loads(download_bytes(exp))
            assert body["name"] == "Multiplier 2.5" and body["params"]["multiplier"] == 2.5
            # import (unknown keys listed) and invalid file
            doc = {"name": "Imported", "params": {"multiplier": 3.0, "colour": "red"}}
            at.get("file_uploader")[-1].set_value(("imp.json", json.dumps(doc).encode(), "application/json")).run()
            assert any("Unknown parameters ignored: colour" in c.value for c in at.caption)
            assert "Imported" in [s["name"] for s in SC.list_all(Path(tmp))]
            at.get("file_uploader")[-1].set_value(("bad.json", b"{oops", "application/json")).run()
            assert any("not a valid scenario" in e.value for e in at.error)
            # delete
            at.selectbox(key="scn_pick").set_value("minimum-10000.json").run()
            at.button(key="scn_delete").click().run()
            assert "Minimum 10000" not in [s["name"] for s in SC.list_all(Path(tmp))]
            check_texts(at, "EN", "lab/scenarios")
    finally:
        shutil.rmtree(tmp)


def _picks() -> dict[str, str]:
    full = simulate(core_data(), Params(), include_all=True)
    a = full[full["is_active"]]
    s = a[a["in_scope"]]
    first = lambda m: a.loc[m, "code"].iloc[0]  # noqa: E731
    return {
        "reliable": first(a["reason_code"].eq("R_FULL_NEED")),
        "caution": first(a["reason_code"].eq("R_COEF_CAUTION")),
        "max_caution": first(a["reason_code"].eq("R_MAX_CAUTION")),
        "not_in_cerved": first(a["reason_code"].eq("R_COEF_NOT_IN_CERVED") & ~a["is_exempt"]),
        "special": first(a["reason_code"].eq("R_SPECIAL")),
        "exempt": first(a["is_exempt"]),
        "minimum": first(a["reason_code"].eq("R_MINIMUM")),
        "ceiling": first(a["reason_code"].eq("R_CERVED_CAP") & a["ceiling_binds"]),
        "hard_cap": first(a["hard_cap_applied"] & ~a["ceiling_binds"]),
        "cerved_zero": first(a["reason_code"].eq("R_CERVED_ZERO")),
        "no_turnover": first(a["reason_code"].eq("R_NO_TURNOVER")),
        "late_payer": first(a["reason_code"].eq("R_BEHAVIOUR_MALUS") & a["in_scope"]),
        "bonus": first(a["reason_code"].eq("R_BEHAVIOUR_BONUS") & a["in_scope"]),
        "tolerance": first(a["behaviour_band"].eq("TOLERANCE") & a["in_scope"]),
        "no_history": first(a["delay_days"].isna() & ~a["is_intercompany"] & ~a["is_special"]),
        "eur": first(a["cerved_currency"].eq("EUR")),
        "intercompany": first(a["is_intercompany"]),
    }


def test_customer_page_for_every_kind_of_customer():
    picks = _picks()
    flat = simulate(core_data(), Params(), include_all=True)
    res = flat.set_index("code")
    with watch():
        for lang in ("EN", "IT"):
            at = go(new_app(lang), "customer")
            lg = lang.lower()
            for kind, code in picks.items():
                at.session_state["customer"] = code
                go(at, "customer")
                assert at.selectbox(key="cust_sel").value == code, kind
                row = res.loc[code]
                boxes = [x.value for x in at.info] + [x.value for x in at.warning]
                text = " ".join(boxes)
                long_ = LG.reason_long(flat.loc[flat["code"] == code].iloc[0], Params(), lg)
                assert long_ in text, (kind, long_, text)
                if kind == "intercompany":
                    assert not at.metric
                    continue
                if row["reason_code"] in LG.ZERO_REASONS:
                    assert at.warning, kind
                m = {x.label: x.value for x in at.metric}
                assert m[TX.T("cust_t_new", lg)] == LG.amt(row["proposed_limit"], lg), kind
                md = [x.value for x in at.markdown]
                steps = next(x for x in md if x.startswith(f"| {TX.T('st_col_n', lg)} |"))
                lines = steps.splitlines()
                assert len(lines) == 2 + 12, kind   # v3.1: the payment-behaviour step is step 7
                assert lines[-1].endswith(f"| **{LG.num(row['proposed_limit'], lg)}** |"), (kind, lines[-1])
                boxes_md = [x for x in md if x.startswith("| **")]
                assert len(boxes_md) == 3, kind
                if kind != "intercompany":   # M1 on contractual terms (v3.1), said under the days box
                    assert any(TX.T("pd_basis_contract", lg, days=LG.num(row["days_used"], lg)) == c.value
                               for c in at.caption), kind
                if kind in ("late_payer", "bonus", "tolerance", "no_history"):
                    band = TX.T("beh_" + row["behaviour_band"], lg)
                    assert any(f"| {TX.T('pd_behaviour', lg)} | {band} (" in b for b in boxes_md), kind
                    assert any(TX.T("st_beh", lg, band=band) in ln for ln in lines), kind
                if kind in ("exempt", "special"):   # not in the order check: never "Over limit: Yes"
                    assert m[TX.T("cust_t_over", lg)] == TX.T("cust_over_not_checked", lg), kind
                if kind == "exempt":
                    assert TX.T("r_EXEMPT_note", lg, cls=row["risk_class"]) in text
                if kind == "eur":
                    assert any(" EUR = " in b for b in boxes_md)
                check_texts(at, lang, f"customer/{kind}/{lang}")


def test_excel_download():
    with watch():
        at = go(new_app("IT"), "results")
        (btn,) = at.get("download_button")
        wb = openpyxl.load_workbook(io.BytesIO(download_bytes(btn)), read_only=True)
        assert wb.sheetnames == ["Clienti", "KPI", "Parametri"]
        ws = wb["Clienti"]
        head = [c.value for c in next(ws.iter_rows(max_row=1))]
        assert "Fido proposto" in head and "Perché questo fido" in head
        assert ws.max_row == 2116 + 1
        params = {r[1]: r[0] for r in wb["Parametri"].iter_rows(min_row=2, values_only=True)}
        assert params["multiplier"] == "Moltiplicatore (× Bisogno M1)"
        kp = {r[1]: r[2] for r in wb["KPI"].iter_rows(min_row=2, values_only=True)}
        assert kp["over_new_n"] == 277


def test_start_with_empty_or_partial_data_folder():
    files = {f.name: f for f in DATA.iterdir()}
    cf = next(f for n, f in files.items() if n.startswith("checkfidi"))
    cv = next(f for n, f in files.items() if n.startswith("cerved"))
    ar = next(f for n, f in files.items() if n.startswith("ar124"))
    for subset, lang in (([], "EN"), ([cf], "IT"), ([cf, cv], "EN"), ([cv, ar], "EN")):
        tmp = tempfile.mkdtemp()
        try:
            for f in subset:
                shutil.copy(f, tmp)
            with env(FIDO_DATA_DIR=tmp), watch():
                at = new_app(lang)
                lg = lang.lower()
                # default page: Data when Check fidi is missing, Results otherwise
                assert at.title[0].value == TX.T("res_title" if cf in subset else "data_title", lg)
                for page in PAGES:
                    go(at, page)
                    check_texts(at, lang, f"{len(subset)} files/{page}")
                go(at, "data")
                badges = " ".join(x.value for x in at.sidebar.markdown)
                if cf not in subset:
                    assert TX.T("badge_data_none", lg) in badges
                    assert any(TX.T("empty_data", lg) in i.value for i in at.info)
                    go(at, "results")
                    assert any(TX.T("empty_results", lg) in i.value for i in at.info)
                elif len(subset) < 3:
                    n_missing = 3 - len(subset)
                    assert (TX.T("badge_data_partial_1", lg) if n_missing == 1 else
                            TX.T("badge_data_partial", lg, n=n_missing)) in badges
                    go(at, "results")
                    warn = " ".join(w.value for w in at.warning)
                    if cv not in subset:
                        assert TX.T("chart_needs_cerved", lg) in " ".join(c.value for c in at.caption)
                        assert "Cerved" in warn
                    if ar not in subset:
                        assert "AR124" in warn
                    assert metrics(at)[TX.T("kpi_over_n", lg)][0]
        finally:
            shutil.rmtree(tmp)


def test_upload_files_into_empty_folder():
    tmp = tempfile.mkdtemp()
    try:
        with env(FIDO_DATA_DIR=tmp), watch():
            at = new_app("EN")
            assert at.title[0].value == TX.T("data_title", "en")
            up = at.file_uploader(key="upload_files")
            bogus = io.BytesIO()
            openpyxl.Workbook().save(bogus)
            payload = [(f.name, f.read_bytes(), "application/octet-stream") for f in sorted(DATA.iterdir()) if f.suffix.lower() in (".xlsx", ".xls")]
            up.set_value(payload + [("notes.xlsx", bogus.getvalue(), "application/octet-stream")]).run()
            assert not at.exception
            assert any('"notes.xlsx" does not look like' in e.value for e in at.error)
            assert any(TX.T("badge_data_ok", "en") in x.value for x in at.sidebar.markdown)
            go(at, "results")
            assert metrics(at)["Over limit, total"][0] == "277"
            go(at, "data")
            assert any("uploaded" in c.value for c in at.caption)
            btn = [b for b in at.button if b.label == TX.T("btn_clear_uploads", "en")][0]
            btn.click().run()
            assert any(TX.T("badge_data_none", "en") in x.value for x in at.sidebar.markdown)
    finally:
        shutil.rmtree(tmp)


def test_data_page_settings_and_quality_details():
    with watch():
        at = go(new_app("EN"), "data")
        m = metrics(at)
        assert m["Active customers"][0] == "2,116" and m["Order-check scope"][0] == "1,598"
        assert m["Reference date"][0] == "20/11/2026"
        sel = at.selectbox(key="dq_pick")
        assert "Duplicate Cerved codes" in sel.options and "Cerved code on two different companies" in sel.options
        sel.set_value(sel.options.index("Cerved code on two different companies")).run()
        assert not at.exception
        at.number_input(key="w_window").set_value(6).run()
        assert at.session_state["params"].window_months == 6
        go(at, "results")
        assert metrics(at)["Over limit, total"][0] == LG.num(expected(Params(window_months=6))["over_new_n"], "en")
        # data settings are not formula changes: no scenario banner
        assert not any("You are looking at scenario" in i.value for i in at.info)


def _write_crafted(folder: Path) -> None:
    """Files with the validator's edge cases: two companies, text amounts, missing optional
    columns, Cerved VAT conflict / other currency / negative limit, text dates, a bad date."""
    import pandas as pd
    from tests.helpers import ar_row, cf_row, cv_row
    cf = pd.DataFrame([cf_row(code="0030001", name="ALFA", t12="120.000,00", balance="12.500,00", vat="RO111"),
                       cf_row(code="30002", name="BETA", t12=1200000, balance=5000, vat="RO222"),
                       cf_row(code="30003", name="GAMMA", t12=1200000, balance=5000, vat="RO333"),
                       cf_row(code="30004", name="DELTA", t12=1200000, balance="oops", vat="RO444"),
                       cf_row(code="30001", name="ALFA OTHER CO", t12=1, balance=1, vat="RO111",
                              **{"Company Code": 43, "Company": "SIAD Other"})])
    cf.to_excel(folder / "cf.xlsx", sheet_name="Result", index=False)
    cv = pd.DataFrame([cv_row(code=30001.0, vat="RO 111", fido=4583),
                       cv_row(code=30002.0, vat="RO 999", name="WRONG CO", fido=0),
                       cv_row(code=30003.0, vat="RO 333", fido=10000, cur="USD"),
                       cv_row(code=30004.0, vat="RO 444", fido=-5)]).drop(columns=["FATTURATO_NO_BIL"])
    cv.to_excel(folder / "cv.xlsx", index=False)
    ar = pd.DataFrame([ar_row(30001, "2026-01-01", "2026-01-31", 100, "2026-02-10")] * 3)
    ar["Invoice Date"] = ["03/02/2026", "15/06/2026", "31/02/2026"]
    ar["Due Date"] = ["05/03/2026", "15/07/2026", "05/03/2026"]
    ar["Date Invoice Closed"] = ["01/04/2026", None, None]
    ar["Gross\nAmount"] = ["1.000,00", "abc", "10"]
    ar.to_excel(folder / "ar.xlsx", index=False)


def test_app_with_edge_case_files():
    """Every page in both languages on crafted edge-case files; every quality check opens."""
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_crafted(tmp)
        d = load_folder(tmp)
        codes = {f.code for f in d.findings}
        assert {"CF_MULTI_COMPANY", "BAD_NUMBERS", "BAD_DATES", "COLUMN_MISSING", "MATCH_VAT_CONFLICT",
                "CV_OTHER_CURRENCY", "CV_NEGATIVE_LIMIT"} <= codes, codes
        assert "FILE_INVALID" not in codes
        res = simulate(d, Params()).set_index("code")
        assert res.loc["30001", "proposed_limit"] == 4583              # hard ceiling 4.583 (whole RON)
        assert not res.loc["30002", "in_cerved"]                         # VAT conflict: not in Cerved
        with env(FIDO_DATA_DIR=str(tmp)), watch():
            for lang in ("EN", "IT"):
                lg = lang.lower()
                at = new_app(lang)
                for page in PAGES:
                    go(at, page)
                    assert not at.exception, page
                    check_texts(at, lang, f"edge/{lang}/{page}")
                go(at, "data")
                sel = at.selectbox(key="dq_pick")
                for label in (TX.T("dq_vat_conflict", lg), TX.T("dq_multi_company", lg),
                              TX.T("dq_bad_numbers", lg), TX.T("dq_bad_dates", lg),
                              TX.T("dq_column_missing", lg), TX.T("dq_other_currency", lg),
                              TX.T("dq_negative_limit", lg)):
                    assert label in sel.options, (label, sel.options)
                for i in range(len(sel.options)):
                    at.selectbox(key="dq_pick").set_value(i).run()
                    assert not at.exception
                    check_texts(at, lang, f"edge/{lang}/data/check {i}")
                for code in ("30001", "30003", "30004"):
                    at.session_state["customer"] = code
                    go(at, "customer")
                    assert not at.exception
                    check_texts(at, lang, f"edge/{lang}/customer {code}")
    finally:
        shutil.rmtree(tmp)


def main() -> int:
    import time
    import traceback
    ok = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            t = time.time()
            try:
                fn()
                ok += 1
                print(f"ok    {name} ({time.time() - t:.1f}s)")
            except Exception:
                print(f"FAIL  {name}")
                traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())


def test_lab_customer_age_bands_on_off():
    """v3.2 customer age in the Lab, IT and EN: bands on / off, thresholds and the minimum of invoices; KPIs
    follow the core; the age table and filter on Results, the badge on Customer, the rule on Rules, the MD105
    card on Data; no exceptions, warnings, untranslated keys or placeholders anywhere."""
    with watch():
        for lang in ("EN", "IT"):
            lg = lang.lower()
            at = go(new_app(lang), "lab")
            lab = lambda: {m.label.rstrip(" •"): m for m in at.metric}  # noqa: E731

            def check(p: Params) -> None:
                k = expected(p)
                m = lab()
                assert m[TX.T("lab_kpi_limits", lg)].value == LG.big(k["limits_proposed_active"], lg)
                assert m[TX.T("lab_kpi_over_pos", lg)].value == LG.num(k["over_new_positive_n"], lg)
                cap = TX.T("lab_age_caption", lg, new=LG.num(k["age_new_n"], lg), young=LG.num(k["age_young_n"], lg),
                           cons=LG.num(k["age_consolidated_n"], lg), none=LG.num(k["age_no_history_n"], lg),
                           bnew=LG.num(k["behaviour_new_n"], lg), bfew=LG.num(k["behaviour_few_n"], lg))
                if p.age_bands_enabled or p.behaviour_min_invoices > 0:
                    assert any(c.value == cap for c in at.caption), cap
                check_texts(at, lang, f"lab/age/{lang}")

            p = Params()
            check(p)
            assert at.toggle(key="w_age_bands_enabled").value and at.number_input(key="w_new_customer_months")
            at.toggle(key="w_age_bands_enabled").set_value(False).run()
            p = p.replace(age_bands_enabled=False)
            check(p)
            assert "w_new_customer_months" not in [x.key for x in at.number_input]   # shown only when on
            at.number_input(key="w_behaviour_min_invoices").set_value(0).run()
            p = p.replace(behaviour_min_invoices=0)
            check(p)
            assert expected(p)["limits_proposed_active"] == 39_970_630           # = v3.1
            at.toggle(key="w_age_bands_enabled").set_value(True).run()
            at.number_input(key="w_new_customer_months").set_value(6).run()
            at.number_input(key="w_consolidated_months").set_value(18).run()
            at.number_input(key="w_behaviour_min_invoices").set_value(4).run()
            p = Params(new_customer_months=6, consolidated_months=18, behaviour_min_invoices=4)
            check(p)
            at.selectbox(key="sens_key").set_value("consolidated_months").run()
            at.button(key="sens_run").click().run()
            assert not at.exception and at.dataframe
            go(at, "results")
            md = " ".join(x.value for x in at.markdown)
            assert TX.T("age_tbl_title", lg) in md and TX.T("age_YOUNG", lg) in md
            assert at.multiselect(key="res_ages")
            at.multiselect(key="res_ages").set_value(["NEW"]).run()
            n_new = int(expected(p)["age_new_n"])
            assert any(c.value.startswith(TX.T("tbl_count", lg, shown=LG.num(n_new, lg), total="").split(" ")[0])
                       for c in at.caption)
            assert not any(TX.T("banner_short_history", lg)[:20] in w.value for w in at.warning)  # MD105 loaded
            check_texts(at, lang, f"results/age/{lang}")
            res = simulate(core_data(), p).set_index("code")
            code = res[res["age_band"].eq("NEW") & res["in_scope"]].index[0]
            at.session_state["customer"] = code
            go(at, "customer")
            assert any(TX.T("age_NEW", lg) in x.value for x in at.markdown)
            assert any(x.value == TX.T("cust_new_warning", lg, months=TX.render("{x:dd}", lg,
                                                                                 x=res.loc[code, "months_active"]))
                       for x in at.warning)
            check_texts(at, lang, f"customer/age/{lang}")
            go(at, "rules")
            assert "MD105" in " ".join(x.value for x in at.markdown)
            check_texts(at, lang, f"rules/age/{lang}")
            go(at, "data")
            assert any(TX.T("file_md105", lg) in x.value for x in at.markdown)
            check_texts(at, lang, f"data/age/{lang}")
            at.sidebar.button(key="sb_reset").click().run()
            go(at, "lab")
            check(Params())


def test_age_bands_without_md105_warn_on_every_page():
    """Folder with the three required files only: the age comes from AR124 (12 months), so the Data page lists
    the coverage finding and Results / Customer show the banner while the bands are on (never disabled)."""
    tmp = tempfile.mkdtemp()
    try:
        for f in DATA.iterdir():
            if "md105" not in f.name:
                shutil.copy(f, tmp)
        with env(FIDO_DATA_DIR=tmp), watch():
            for lang in ("EN", "IT"):
                lg = lang.lower()
                banner = TX.T("banner_short_history", lg, months="12", needed="18")
                at = go(new_app(lang), "results")
                assert any(w.value == banner for w in at.warning), [w.value for w in at.warning]
                go(at, "customer")
                assert any(w.value == banner for w in at.warning)
                # left-censored customer (first invoice at the start of AR124): consolidated, "≥ N months"
                if "d3" not in _CORE:
                    from core.loaders import load_files
                    _CORE["d3"] = load_files(sorted(Path(tmp).iterdir()))
                r3 = simulate(_CORE["d3"], Params())
                code = r3[r3["age_censored"] & r3["in_scope"]]["code"].iloc[0]
                at.session_state["customer"] = code
                go(at, "customer")
                md = " ".join(x.value for x in at.markdown)
                assert "≥" in md and TX.T("age_CONSOLIDATED", lg) in md
                check_texts(at, lang, f"customer/censored/{lang}")
                go(at, "data")
                md = " ".join(x.value for x in at.markdown)
                assert TX.T("dq_ar_short_history", lg) in md and TX.T("file_md105", lg) in md
                check_texts(at, lang, f"data/no-md105/{lang}")
                go(at, "lab")
                at.toggle(key="w_age_bands_enabled").set_value(False).run()
                go(at, "results")
                assert not any(w.value == banner for w in at.warning)
                check_texts(at, lang, f"results/no-md105/{lang}")
    finally:
        shutil.rmtree(tmp)
