"""Shared Streamlit state: language, active parameters, cached data loading and simulation,
page header and sidebar. Pages import this module; the calculation stays in ``core``.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from core import texts as TX
from core.engine import reference_date
from core.export import to_excel
from core.kpi import kpis
from core.loaders import Finding, LoadedData, load_files
from core.params import Params
from ui import logic as LG

APP_DIR = Path(__file__).resolve().parent.parent
PAGE_FILES = {"data": "ui/pages/data.py", "results": "ui/pages/results.py",
              "customer": "ui/pages/customer.py", "lab": "ui/pages/lab.py", "rules": "ui/pages/rules.py"}
WIDGET_PREFIX = "w_"   # Lab / Data-settings widgets mirroring parameters (reset by set_params)


# ---------------------------------------------------------------------------
# Folders (environment variables let tests point elsewhere)
# ---------------------------------------------------------------------------
def data_dir() -> Path | None:
    """Folder to auto-load files from. The app starts empty: files are uploaded on the Data page.
    Auto-loading happens only when the FIDO_DATA_DIR environment variable points to a folder
    (used by the tests and by anyone who wants a pre-filled start)."""
    v = os.environ.get("FIDO_DATA_DIR")
    return Path(v) if v else None


def workspace_dir() -> Path:
    p = Path(os.environ.get("FIDO_WORKSPACE_DIR") or APP_DIR / "workspace")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
def lang() -> str:
    return st.session_state.get("lang_code", "en")


def L(key: str, **values: Any) -> str:
    """UI text in the active language."""
    return TX.T(key, lang(), **values)


def _on_lang() -> None:
    v = st.session_state.get("lang_seg")
    if v is None:  # segmented control deselected: keep the current language
        st.session_state.lang_seg = lang().upper()
    else:
        st.session_state.lang_code = v.lower()


# ---------------------------------------------------------------------------
# Parameters and scenario name
# ---------------------------------------------------------------------------
def init_state() -> None:
    ss = st.session_state
    ss.setdefault("lang_code", "en")
    ss.setdefault("params", Params())
    ss.setdefault("scn_name", None)     # name of the saved/loaded scenario
    ss.setdefault("scn_json", None)     # its parameters, to know if it is still the active one
    ss.setdefault("uploads", [])        # [(name, bytes)] uploaded on the Data page


def params() -> Params:
    return st.session_state.params


def set_params(p: Params, name: str | None = None) -> None:
    """Make ``p`` the active scenario and re-sync every parameter widget from it."""
    ss = st.session_state
    ss.params = p
    if name is not None:
        ss.scn_name, ss.scn_json = name, p.to_json()
    for k in [k for k in ss.keys() if str(k).startswith(WIDGET_PREFIX)]:
        del ss[k]


def reset_params() -> None:
    """Back to the v3 formula (data settings are kept)."""
    set_params(LG.base_params(params()))
    st.session_state.scn_name = st.session_state.scn_json = None


def scenario_name() -> str:
    ss = st.session_state
    if ss.scn_name and ss.scn_json == params().to_json():
        return ss.scn_name
    return L("scn_unsaved")


# ---------------------------------------------------------------------------
# Data loading (cached: parsing the three files takes a few seconds)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=8)
def _read_folder(folder: str, sig: tuple) -> list[tuple[str, str, bytes]]:
    out = []
    for name, _mtime, _size in sig:
        b = (Path(folder) / name).read_bytes()
        out.append((name, hashlib.md5(b).hexdigest(), b))
    return out


def _folder_entries() -> list[tuple[str, str, bytes]]:
    folder = data_dir()
    if folder is None or not folder.is_dir():
        return []
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in (".xls", ".xlsx")
                   and not f.name.startswith("~$"))
    sig = tuple((f.name, f.stat().st_mtime, f.stat().st_size) for f in files)
    return _read_folder(str(folder), sig)


@st.cache_resource(show_spinner=False, max_entries=24)
def _parse(digest: str, name: str, _data: bytes) -> LoadedData:
    return load_files([(name, _data)])


@st.cache_resource(show_spinner=False, max_entries=8)
def _combine(key: tuple, _parts: tuple) -> LoadedData:
    """One LoadedData from single-file parses; earlier parts (uploads) win per file kind."""
    ld = LoadedData()
    origin: dict[str, str] = {}
    for (name, _digest, src), part in zip(key, _parts):
        for f in part.findings:
            if f.code == "FILE_INVALID":
                ld.findings.append(f)
        for kind, fname in part.sources.items():
            if kind in ld.sources:
                if origin[kind] == src:  # two files of the same kind from the same place
                    ld.findings.append(Finding("FILE_DUPLICATE_KIND", "warning", 1, [fname],
                                               {"kind": kind, "kept": ld.sources[kind]}))
                continue
            attr = "ar" if kind == "ar124" else kind
            setattr(ld, attr, getattr(part, attr))
            ld.sources[kind] = fname
            ld.rows_read[kind] = part.rows_read[kind]
            origin[kind] = src
            ld.findings.extend(f for f in part.findings if f.code != "FILE_INVALID"
                               and not f.code.startswith(("MISSING_", "MATCH_", "CV_UNMATCHED")))
    return ld.finalize()


def get_data() -> tuple[LoadedData, tuple]:
    """(data, key). Uploaded files replace the data/ file of the same kind."""
    entries = [(n, hashlib.md5(b).hexdigest(), b, "upload") for n, b in st.session_state.uploads]
    entries += [(n, d, b, "folder") for n, d, b in _folder_entries()]
    key = tuple((n, d, src) for n, d, _b, src in entries)
    if key in st.session_state.get("_loaded_keys", set()):
        parts = tuple(_parse(d, n, b) for n, d, b, _s in entries)
        return _combine(key, parts), key
    with st.spinner(L("loading_files")):
        parts = tuple(_parse(d, n, b) for n, d, b, _s in entries)
        data = _combine(key, parts)
    st.session_state.setdefault("_loaded_keys", set()).add(key)
    return data, key


def uploaded_kinds(data: LoadedData) -> set[str]:
    names = {n for n, _b in st.session_state.uploads}
    return {k for k, n in data.sources.items() if n in names}


# ---------------------------------------------------------------------------
# Simulation (cached per data and parameter set)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=48)
def _simulate(key: tuple, pjson: str, _data: LoadedData) -> dict[str, Any]:
    from core.engine import simulate
    full = simulate(_data, Params.from_json(pjson), include_all=True)
    active = full[full["is_active"]].reset_index(drop=True)
    res = active[~active["is_intercompany"]].reset_index(drop=True)
    k = kpis(res)
    k["zero_with_turnover_current_n"] = int(((res["current_limit"] <= 0) & (res["turnover_12m"] > 0)
                                             & ~res["is_special"]).sum())
    return {"all": active, "res": res, "kpi": k}


def simulate(data: LoadedData, key: tuple, p: Params | None = None) -> dict[str, Any]:
    """{"res": active customers without intercompany, "all": active incl. intercompany, "kpi"}."""
    return _simulate(key, (p or params()).to_json(), data)


@st.cache_resource(show_spinner=False, max_entries=8)
def _table(key: tuple, pjson: str, lng: str, _res: pd.DataFrame) -> pd.DataFrame:
    return LG.customer_table(_res, Params.from_json(pjson), lng)


def customer_table(key: tuple, res: pd.DataFrame) -> pd.DataFrame:
    return _table(key, params().to_json(), lang(), res)


@st.cache_resource(show_spinner=False, max_entries=4)
def _excel(key: tuple, pjson: str, lng: str, _res: pd.DataFrame) -> bytes:
    return to_excel(_res, Params.from_json(pjson), lng)


def excel_bytes(key: tuple, res: pd.DataFrame) -> bytes:
    return _excel(key, params().to_json(), lang(), res)


def ref_date(data: LoadedData) -> pd.Timestamp:
    return reference_date(data, params())


# ---------------------------------------------------------------------------
# Page frame
# ---------------------------------------------------------------------------
def missing_banners(data: LoadedData) -> None:
    """One warning per missing input file (only when Check fidi is there)."""
    if not data.ok:
        return
    p, lg = params(), lang()
    if "cerved" in data.missing:
        st.warning(L("missing_cerved_impact", coef=LG.coef(p.coef_not_in_cerved, lg)), icon=":material/warning:")
    if "ar124" in data.missing:
        st.warning(L("missing_ar124_impact", days=LG.num(p.fallback_days, lg)), icon=":material/warning:")


def coverage_banner(data: LoadedData) -> None:
    """Results / Customer pages: age bands on and ages from AR124 only with a short file (no MD105)."""
    if not data.ok:
        return
    from core.engine import coverage_finding
    f = coverage_finding(data, params())
    if f is not None:
        st.warning(L("banner_short_history", months=TX.render("{x:dd}", lang(), x=f.details["months"]),
                     needed=LG.num(f.details["needed"], lang())), icon=":material/history:")


def page_header(prefix: str, data: LoadedData, banner: bool = True) -> None:
    st.title(L(f"{prefix}_title"))
    st.caption(L(f"{prefix}_subtitle"))
    if banner:
        n, changes = LG.formula_changes(params(), lang())
        if n:
            st.info(L("banner_scenario", name=scenario_name(), changes=changes), icon=":material/tune:")
    missing_banners(data)


def no_data(data: LoadedData) -> bool:
    """Without Check fidi: say so, link to the Data page, return True."""
    if data.ok:
        return False
    st.info(L("empty_results"), icon=":material/folder_open:")
    st.page_link(PAGE_FILES["data"], label=L("go_data"), icon=":material/folder_open:")
    return True


APP_VERSION = "3.6 · 22/11/2026"

CSS = """
<style>
/* tabs: large and clearly visible (Customer page); old and new Streamlit markup */
[role="tablist"] { gap: 0.5rem; border-bottom: 2px solid rgba(15, 72, 129, 0.25); }
[role="tab"] { padding: 0.6rem 1.1rem !important; border-radius: 8px 8px 0 0;
  background: rgba(15, 72, 129, 0.07); }
[role="tab"][aria-selected="true"] { background: rgba(15, 72, 129, 0.18); }
[role="tab"] p, [role="tab"] span { font-size: 17px !important; font-weight: 600; }
html, body, [class*="stMarkdown"] p, [data-testid="stCaptionContainer"] { font-size: 17px; }
[data-testid="stMainBlockContainer"], .block-container { padding-top: 2.2rem; }
[data-testid="stMetricLabel"] p { font-size: 16px; }
/* KPI values large for the projector. The generic "stMarkdown p" rule above must not shrink them:
   the value is rendered inside a markdown container, so the size is forced on every descendant. */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
  font-size: 1.75rem !important; line-height: 1.2 !important; font-weight: 600; }
[data-testid="stMetricValue"] * { white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; overflow-wrap: normal !important; }
[data-testid="stMetricDelta"], [data-testid="stMetricDelta"] div { font-size: 15px !important; }
/* projector: tile labels and deltas wrap instead of being cut with "..." */
[data-testid="stMetricLabel"] *, [data-testid="stMetricDelta"] * {
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
  word-break: normal !important; overflow-wrap: normal !important; }
[data-testid="stMetricDelta"] { height: auto !important; }
[data-testid="stTable"] td, [data-testid="stTable"] th { font-size: 16px; }
</style>
"""

# Italian number format on sliders: Streamlit formats the thumb value and the min / max with
# sprintf (always "1.25"); in Italian those are hidden and the label carries the formatted value.
CSS_IT_SLIDERS = """
<style>
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBar"] { visibility: hidden; }
</style>
"""


def sidebar(data: LoadedData) -> None:
    """Sidebar below the navigation: title, language, data and scenario badges."""
    ss = st.session_state
    ss.setdefault("lang_seg", lang().upper())
    with st.sidebar:
        st.markdown("### " + L("app_title"))
        st.caption(L("app_subtitle"))
        st.segmented_control(L("lang_label"), ["IT", "EN"], key="lang_seg", on_change=_on_lang)
        st.divider()
        missing = data.missing
        if not data.ok:
            st.markdown(f":gray-badge[{L('badge_data_none')}]")
        elif missing:
            txt = L("badge_data_partial_1") if len(missing) == 1 else L("badge_data_partial", n=len(missing))
            st.markdown(f":orange-badge[:material/warning: {txt}]")
        else:
            st.markdown(f":green-badge[:material/check: {L('badge_data_ok')}]")
        if data.ok:
            st.caption(L("badge_ref_date", date=LG.date_str(ref_date(data))))
        n, _changes = LG.formula_changes(params(), lang())
        if n:
            st.markdown(f":violet-badge[{L('badge_scn_modified', n=n)}]")
            if ss.scn_name and ss.scn_json == params().to_json():
                st.caption(L("badge_scn_name", name=ss.scn_name))
            st.button(L("btn_reset_defaults"), key="sb_reset", help=L("btn_reset_help"),
                      icon=":material/restart_alt:", on_click=reset_params)
        else:
            st.markdown(f":blue-badge[{L('badge_scn_default')}]")
        st.caption(L("app_version", v=APP_VERSION))


def styler(df: pd.DataFrame, money: list[str], signed: list[str] | None = None,
           bold: list[str] | None = None, counts: list[str] | None = None) -> Any:
    """Pandas Styler with IT/EN number format; keeps numeric dtypes for sorting."""
    lg = lang()
    fm: dict[str, Any] = {c: (lambda v, lg=lg: LG.num(v, lg)) for c in money + (counts or [])}
    for c in signed or []:
        fm[c] = lambda v, lg=lg: "-" if pd.isna(v) else LG.signed(v, lg)
    sty = df.style.format(fm, na_rep="-")
    for c in bold or []:
        sty = sty.set_properties(subset=[c], **{"font-weight": "bold"})
    for c in signed or []:
        sty = sty.map(lambda v: "color: #2E75B6" if isinstance(v, (int, float)) and v > 0.5
                      else ("color: #D9822B" if isinstance(v, (int, float)) and v < -0.5 else ""), subset=[c])
    return sty


def md_table(header: list[str], rows: list[list[str]], align: str | None = None, bold_last: bool = False) -> str:
    """Static Markdown table (large on a projector, no index, no scrollbars).

    ``align``: one letter per column, "l" or "r". Pipes in cells are escaped.
    """
    esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ") if str(v) != "" else " "  # noqa: E731
    align = align or "l" * len(header)
    out = ["| " + " | ".join(esc(h) for h in header) + " |",
           "|" + "|".join("---:" if a == "r" else ":---" for a in align) + "|"]
    for i, r in enumerate(rows):
        cells = [esc(c) for c in r]
        if bold_last and i == len(rows) - 1:
            cells = [f"**{c}**" if c.strip() else c for c in cells]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)
