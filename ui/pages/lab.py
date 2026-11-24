"""Page "Laboratorio / Lab": which formula works best? (UX.md section 5)

Every control writes into the active parameter set (st.session_state.params); the whole app
follows it. Widgets mirror parameters through keys "w_<param>" seeded from the parameters,
so Reset / Load only have to change the parameters and drop those keys (common.set_params).
"""
from __future__ import annotations

from typing import Any, Callable

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from core import country as CO
from core.kpi import changed_customers
from core.params import Params
from core.sensitivity import sensitivity
from core import texts as TX
from ui import common as C
from ui import logic as LG
from ui import scenarios as SC

ss = st.session_state
lg = C.lang()


def tl(k: str) -> str:
    """Text in this run's language without touching session state (safe in format_func)."""
    return TX.T(k, lg)

data, key = C.get_data()

C.page_header("lab", data, banner=False)
if C.no_data(data):
    st.stop()

p0 = C.params()
SF = CO.active().step_factor   # local-currency inputs: Romanian steps x this (EUR: 0,25)
base = LG.base_params(p0)


# ---------------------------------------------------------------------------
# Parameter controls
# ---------------------------------------------------------------------------
def _pct_in(v: float) -> int:
    return int(round(v * 100))


def _r4(v: Any) -> float:
    return round(float(v), 4)


# param -> (to widget value, from widget value)
CONV: dict[str, tuple[Callable[[Any], Any], Callable[[Any], Any]]] = {
    "buffer": (_pct_in, lambda v: v / 100), "plausibility_threshold": (_pct_in, lambda v: v / 100),
    "approval_threshold": (_pct_in, lambda v: v / 100),
    "multiplier": (float, _r4), "coef_reliable": (float, _r4), "coef_caution": (float, _r4),
    "coef_max_caution": (float, _r4), "coef_not_in_cerved": (float, _r4),
    "coef_exempt_not_in_cerved": (float, _r4), "eur_rate": (float, _r4),
    "min_days": (int, int), "fallback_days": (int, int), "cap_extra_days": (int, int),
    "rounding_step": (int, int), "min_limit": (int, int), "tier1_eur": (int, float), "tier2_eur": (int, float),
    "approval_min_change": (int, int),
    "behaviour_bonus_max": (_pct_in, lambda v: v / 100), "behaviour_malus_max": (_pct_in, lambda v: v / 100),
    "behaviour_tolerance_days": (int, int), "behaviour_full_malus_days": (int, int),
    "behaviour_enabled": (bool, bool), "m1_days_basis": (str, str),
    "age_bands_enabled": (bool, bool), "new_customer_months": (int, int), "consolidated_months": (int, int),
    "behaviour_min_invoices": (int, int),
    "cap_days_enabled": (bool, bool), "cerved_cap_enabled": (bool, bool),
    "rounding_mode": (str, str), "intercompany_codes": (list, list), "special_classes": (list, list),
    "exempt_classes": (list, list),
}
values: dict[str, Any] = {}


def wkey(k: str) -> str:
    return C.WIDGET_PREFIX + k


def current(k: str) -> Any:
    """Seed the widget from the parameters if needed; return the parameter value it holds."""
    to_ui, from_ui = CONV[k]
    if wkey(k) not in ss:
        ss[wkey(k)] = to_ui(getattr(p0, k))
    v = ss[wkey(k)]
    if v is None:  # segmented control deselected: keep the current value
        v = to_ui(getattr(p0, k))
        ss[wkey(k)] = v
    values[k] = from_ui(v)
    return values[k]


def _clean_list(k: str, v: list) -> list[str]:
    return [str(x).strip() if k == "intercompany_codes" else str(x).strip().upper() for x in v if str(x).strip()]


def _sync() -> None:
    """on_change of every control: rebuild the active parameters from the widgets.

    Runs before the script, so the sidebar badge and banners are already up to date."""
    d: dict[str, Any] = {}
    for k, (_to_ui, from_ui) in CONV.items():
        v = ss.get(wkey(k))
        if v is not None:
            d[k] = _clean_list(k, v) if isinstance(v, list) else from_ui(v)
    new = C.params().replace(**d)
    if new.tier2_eur < new.tier1_eur:
        new = new.replace(tier2_eur=new.tier1_eur)
    new = _fix_full_malus(new)
    new = _fix_age(new)
    if not new.validate():
        ss.params = new


def _fix_full_malus(new: Params) -> Params:
    """The full-malus days must stay above the tolerance: raising the tolerance pushes them up."""
    if new.behaviour_full_malus_days <= new.behaviour_tolerance_days:
        new = new.replace(behaviour_full_malus_days=new.behaviour_tolerance_days + 1)
        ss[wkey("behaviour_full_malus_days")] = new.behaviour_full_malus_days
    return new


def _fix_age(new: Params) -> Params:
    """The consolidated threshold must stay at or above the new-customer one: raising the latter pushes it up."""
    if new.consolidated_months < new.new_customer_months:
        new = new.replace(consolidated_months=new.new_customer_months)
        ss[wkey("consolidated_months")] = new.consolidated_months
    return new


def label(k: str, text_key: str, show_value: bool = False) -> str:
    """Label with a bullet when the value differs from v3 (visible without colour). With
    ``show_value`` the value follows in the language's number format ("Fido minimo (RON): 5.000"):
    Streamlit formats slider and number-input values with sprintf (always "1.25", "5000")."""
    changed = values[k] != getattr(base, k)
    txt = C.L(text_key)
    if show_value:
        txt += f": **{LG.param_value(k, values[k], lg)}**"
    return txt + (" •" if changed else "")


IT_SLIDERS = lg == "it"   # Italian: native slider numbers hidden (CSS), value in the label
if IT_SLIDERS:
    st.markdown(C.CSS_IT_SLIDERS, unsafe_allow_html=True)


def slider(k: str, text_key: str, lo: float, hi: float, step: float, fmt: str, disabled: bool = False) -> None:
    v = CONV[k][0](getattr(p0, k)) if wkey(k) not in ss else ss[wkey(k)]
    lo, hi = min(lo, v), max(hi, v)  # imported scenarios may be outside the usual range
    current(k)
    st.slider(label(k, text_key, IT_SLIDERS), lo, hi, step=step, format=fmt, key=wkey(k),
              help=C.L(text_key + "_help"), disabled=disabled, on_change=_sync)


def number(k: str, text_key: str, lo: float, hi: float, step: float, help_key: str | None = None,
           fmt: str | None = None, show_value: bool = False) -> None:
    v = CONV[k][0](getattr(p0, k)) if wkey(k) not in ss else ss[wkey(k)]
    lo, hi = min(lo, v), max(hi, v)
    current(k)
    st.number_input(label(k, text_key, show_value or (IT_SLIDERS and fmt is not None)), min_value=lo,
                    max_value=hi, step=step, key=wkey(k), format=fmt,
                    help=C.L(help_key or text_key + "_help"), on_change=_sync)


def toggle(k: str, text_key: str, disabled: bool = False) -> None:
    current(k)
    st.toggle(label(k, text_key), key=wkey(k), help=C.L(text_key + "_help"), on_change=_sync, disabled=disabled)


def lists(k: str, text_key: str, extra: list[str]) -> None:
    current(k)
    opts = sorted(set(extra) | set(getattr(base, k)) | set(ss[wkey(k)]))
    st.multiselect(label(k, text_key), opts, key=wkey(k), accept_new_options=True, help=C.L("p_lists_help"),
                   on_change=_sync)
    values[k] = _clean_list(k, ss[wkey(k)])


left, right = st.columns([1, 2.3], gap="large")
with left:
    st.button(C.L("btn_reset_defaults"), icon=":material/restart_alt:", width="stretch",
              help=C.L("btn_reset_help"), on_click=C.reset_params, key="lab_reset")
    changed_caption = st.empty()
    # no fixed-height container: at 768 px a nested scroll area is hard to use on a projector
    with st.container(border=False):
        with st.container(border=True):
            st.markdown(f"**{C.L('grp_need')}**")
            slider("buffer", "p_buffer_pct", 0, 50, 5, "%d%%")
            slider("multiplier", "p_multiplier", 1.0, 4.0, 0.25, "%.2f ×")
            current("m1_days_basis")
            st.segmented_control(label("m1_days_basis", "p_m1_basis"), ["contractual", "measured"],
                                 key=wkey("m1_days_basis"), help=C.L("p_m1_basis_help"), on_change=_sync,
                                 format_func=lambda v: tl("p_m1_measured" if v == "measured" else "p_m1_contractual"))
            on_terms = values["m1_days_basis"] == "contractual"   # the maximum only matters on measured days
            number("min_days", "p_days_min", 0, 60, 5)
            toggle("cap_days_enabled", "p_days_cap_on", disabled=on_terms)
            slider("cap_extra_days", "p_days_over_terms", 0, 90, 5, "%d",
                   disabled=on_terms or not values["cap_days_enabled"])
            number("fallback_days", "p_days_default", 15, 120, 5)
        with st.container(border=True):
            st.markdown(f"**{C.L('grp_risk')}**")
            slider("coef_reliable", "p_coef_reliable", 0.0, 1.0, 0.05, "%.2f")
            slider("coef_caution", "p_coef_caution", 0.0, 1.0, 0.05, "%.2f")
            slider("coef_max_caution", "p_coef_max_caution", 0.0, 1.0, 0.05, "%.2f")
            slider("coef_not_in_cerved", "p_coef_not_in_cerved", 0.0, 1.0, 0.05, "%.2f")
        with st.container(border=True):
            st.markdown(f"**{C.L('grp_behaviour')}**")
            toggle("behaviour_enabled", "p_behaviour_on")
            if values["behaviour_enabled"]:   # the four values only matter (and are shown) when it is on
                slider("behaviour_bonus_max", "p_beh_bonus", 0, 20, 1, "%d%%")
                slider("behaviour_malus_max", "p_beh_malus", 0, 30, 1, "%d%%")
                number("behaviour_tolerance_days", "p_beh_tol", 0, 60, 1, show_value=IT_SLIDERS)
                current("behaviour_tolerance_days")
                number("behaviour_full_malus_days", "p_beh_full", int(values["behaviour_tolerance_days"]) + 1,
                       365, 5, show_value=IT_SLIDERS)
            else:
                for k in ("behaviour_bonus_max", "behaviour_malus_max", "behaviour_tolerance_days",
                          "behaviour_full_malus_days"):
                    current(k)
        with st.container(border=True):
            st.markdown(f"**{C.L('grp_age')}**")
            toggle("age_bands_enabled", "p_age_on")
            if values["age_bands_enabled"]:   # the two thresholds only matter (and are shown) when it is on
                number("new_customer_months", "p_age_new", 0, 36, 1, show_value=IT_SLIDERS)
                number("consolidated_months", "p_age_consolidated", max(1, int(values["new_customer_months"])),
                       60, 1, show_value=IT_SLIDERS)
            else:
                for k in ("new_customer_months", "consolidated_months"):
                    current(k)
            number("behaviour_min_invoices", "p_beh_min_inv", 0, 100, 1, show_value=IT_SLIDERS)
        with st.container(border=True):
            st.markdown(f"**{C.L('grp_caps')}**")
            toggle("cerved_cap_enabled", "p_cerved_cap_on")
            current("rounding_step")
            steps = sorted(set(CO.active().rounding_choices()) | {int(ss[wkey("rounding_step")])})
            st.segmented_control(label("rounding_step", "p_round_step"), steps, key=wkey("rounding_step"),
                                 format_func=lambda v: LG.num(v, lg), help=C.L("p_round_step_help"),
                                 on_change=_sync)
            number("min_limit", "p_min_limit", 0, int(50000 * SF), max(1, int(1000 * SF)), show_value=True)
        with st.container(border=True):
            st.markdown(f"**{C.L('grp_checks')}**")
            slider("plausibility_threshold", "p_plaus_pct", 1, 50, 1, "%d%%")
            slider("approval_threshold", "p_approval_pct", 0, 100, 5, "%d%%")
    with st.expander(C.L("grp_other")):
        number("approval_min_change", "p_approval_min", 0, int(1_000_000 * SF), max(1, int(1000 * SF)), show_value=True)
        current("rounding_mode")
        st.segmented_control(label("rounding_mode", "p_round_dir"), ["up", "down"], key=wkey("rounding_mode"),
                             format_func=lambda v: tl("p_round_up" if v == "up" else "p_round_down"),
                             on_change=_sync)
        slider("coef_exempt_not_in_cerved", "p_coef_exempt_nf", 0.0, 1.0, 0.05, "%.2f")
        if CO.active().currency != "EUR":   # a euro country has nothing to convert
            r0 = CO.active().eur_rate
            number("eur_rate", "p_eur_rate", round(r0 * 0.8, 3), round(r0 * 1.25, 3), 0.001 if r0 < 50 else 0.1,
                   fmt="%.3f" if r0 < 50 else "%.1f")
        else:
            current("eur_rate")
        number("tier1_eur", "p_tier1", 0, 10_000_000, 10000, help_key="p_tier_help", show_value=True)
        number("tier2_eur", "p_tier2", 0, 10_000_000, 10000, help_key="p_tier_help", show_value=True)
        classes = sorted({c for c in data.customers["risk_class"].dropna().unique() if c})
        lists("intercompany_codes", "p_intercompany", [])
        lists("special_classes", "p_special", classes)
        lists("exempt_classes", "p_exempt", classes)

    new_p = p0.replace(**values)
    if values["tier2_eur"] < values["tier1_eur"]:
        new_p = new_p.replace(tier2_eur=values["tier1_eur"])
    if new_p.behaviour_full_malus_days <= new_p.behaviour_tolerance_days:
        new_p = new_p.replace(behaviour_full_malus_days=new_p.behaviour_tolerance_days + 1)
    if new_p.consolidated_months < new_p.new_customer_months:
        new_p = new_p.replace(consolidated_months=new_p.new_customer_months)
    errs = new_p.validate()
    if errs:
        st.error("; ".join(errs))
    elif new_p.to_json() != p0.to_json():
        ss.params = new_p
    p = C.params()
    n_ch, ch_list = LG.formula_changes(p, lg)
    changed_caption.caption(C.L("lab_changed", list=ch_list) if n_ch else C.L("lab_unchanged"))

# ---------------------------------------------------------------------------
# Right: KPIs scenario vs v3, then tabs
# ---------------------------------------------------------------------------
with right:
    scn = C.simulate(data, key, p)
    bas = C.simulate(data, key, base)
    ks, kb = scn["kpi"], bas["kpi"]
    same = p.to_json() == base.to_json()

    st.markdown("<style>[data-testid='stMetricValue'], [data-testid='stMetricValue'] * "
                "{ font-size: 1.6rem !important; }</style>", unsafe_allow_html=True)  # narrower column

    def tile(col: Any, label_key: str, kpi: str, money: bool, color: str, **lab: Any) -> None:
        v, b = ks[kpi], kb[kpi]
        d = v - b
        if money:
            in_m = abs(v) >= 1e6
            val, base_txt = LG.big(v, lg), LG.big(b, lg)
            dtxt = C.L("lab_delta", d=LG.signed_big(d, lg, in_m))
        else:
            val, base_txt = LG.num(v, lg), LG.num(b, lg)
            dtxt = C.L("lab_delta", d=LG.signed(d, lg))
        col.metric(C.L(label_key, **lab), val, None if same or abs(d) < 0.5 else dtxt, delta_color=color,
                   border=True, help=C.L("lab_help_base", v=base_txt))

    # headline: over a positive limit; the total keeps the customers at limit 0 by rule visible
    t = st.columns(4)   # counts (short values) on the first row, amounts on the second
    tile(t[0], "lab_kpi_over_pos", "over_new_positive_n", False, "inverse")
    with t[1]:
        tile(st, "lab_kpi_over_n", "over_new_n", False, "off")
        st.caption(C.L("lab_over_split", z=LG.num(ks["over_new_zero_n"], lg)))
    tile(t[2], "lab_kpi_zero", "zero_with_turnover_n_active", False, "off")
    tile(t[3], "lab_kpi_approval", "approval_n", False, "off")
    t = st.columns(3)
    tile(t[0], "lab_kpi_over_amt", "excess_new", True, "inverse")
    tile(t[1], "lab_kpi_limits_scope", "limits_proposed_scope", True, "off")
    tile(t[2], "lab_kpi_limits", "limits_proposed_active", True, "off")
    st.caption(C.L("lab_current_ref", pos=LG.num(ks["over_current_positive_n"], lg),
                   over=LG.num(ks["over_current_n"], lg), amt=LG.big(ks["excess_current"], lg)))
    if p.behaviour_enabled:   # payment bonus / malus: who gets it and its net effect on the limits
        t = st.columns(3)
        tile(t[0], "lab_kpi_bonus", "behaviour_bonus_n", False, "off")
        tile(t[1], "lab_kpi_malus", "behaviour_malus_n", False, "off")
        tile(t[2], "lab_kpi_beh_effect", "behaviour_effect_active", True, "off")
        st.caption(C.L("lab_beh_caption", tol=LG.num(ks["behaviour_tolerance_n"], lg),
                       none=LG.num(ks["behaviour_no_history_n"], lg),
                       scope=LG.signed_big(ks["behaviour_effect_scope"], lg, abs(ks["behaviour_effect_scope"]) >= 1e6)))

    if p.age_bands_enabled or p.behaviour_min_invoices > 0:   # v3.2: customers by age, bonus / malus gates
        st.caption(C.L("lab_age_caption", new=LG.num(ks["age_new_n"], lg), young=LG.num(ks["age_young_n"], lg),
                       cons=LG.num(ks["age_consolidated_n"], lg), none=LG.num(ks["age_no_history_n"], lg),
                       bnew=LG.num(ks["behaviour_new_n"], lg), bfew=LG.num(ks["behaviour_few_n"], lg)))

    tab_e, tab_s, tab_c = st.tabs([C.L("tab_effect"), C.L("tab_sens"), C.L("tab_scn")])

    # --- Effect ------------------------------------------------------------
    with tab_e:
        ch = changed_customers(bas["res"], scn["res"])
        if ch.empty:
            st.info(C.L("chg_none"), icon=":material/info:")
        else:
            up, down = int((ch["delta"] > 0.5).sum()), int((ch["delta"] < -0.5).sum())
            into = int((ch["over_new_scenario"] & ~ch["over_new_base"]).sum())
            out = int((~ch["over_new_scenario"] & ch["over_new_base"]).sum())
            st.caption(C.L("chg_summary", n=LG.num(len(ch), lg), up=LG.num(up, lg), down=LG.num(down, lg),
                           into=LG.num(into, lg), out=LG.num(out, lg)))
            ss.setdefault("chg_filter", "ALL")
            flt = st.segmented_control(C.L("chg_filter_label"), ["ALL", "LIMIT", "OVER_STATUS"], key="chg_filter",
                                       format_func=lambda x: tl({"ALL": "chg_filter_all", "LIMIT": "chg_filter_limit",
                                                                  "OVER_STATUS": "chg_filter_status"}[x]))
            if flt == "LIMIT":
                ch = ch[ch["change"].isin(["LIMIT", "BOTH"])]
            elif flt == "OVER_STATUS":
                ch = ch[ch["change"].isin(["OVER_STATUS", "BOTH"])]
            sres = scn["res"].set_index("code")
            why = [LG.reason_short(sres.loc[c], p, lg) if c in sres.index else "" for c in ch["code"]]
            view = pd.DataFrame({
                "code": ch["code"].values, "name": ch["name"].values,
                "score": [LG.score_label(b, lg) for b in ch["score_bucket"]],
                "exposure": ch["exposure"].values, "v3": ch["proposed_limit_base"].values,
                "scn": ch["proposed_limit_scenario"].values, "delta": ch["delta"].values,
                "over": [LG.over_text(a, b, lg) for a, b in zip(ch["over_new_base"], ch["over_new_scenario"])],
                "why": why}).reset_index(drop=True)
            cc = st.column_config
            cfg = {"code": cc.TextColumn(C.L("col_code"), width="small"), "name": cc.TextColumn(C.L("col_name")),
                   "score": cc.TextColumn(C.L("col_score"), width="small"),
                   "exposure": cc.NumberColumn(C.L("col_exposure")), "v3": cc.NumberColumn(C.L("chg_col_v3")),
                   "scn": cc.NumberColumn(C.L("chg_col_scn")), "delta": cc.NumberColumn(C.L("col_diff")),
                   "over": cc.TextColumn(C.L("chg_col_over"), width="small"),
                   "why": cc.TextColumn(C.L("chg_col_why"), width="medium")}
            slot = st.empty()
            if view.empty:
                st.info(C.L("tbl_empty"), icon=":material/filter_alt_off:")
            else:
                ev = st.dataframe(C.styler(view, ["exposure", "v3", "scn"], signed=["delta"], bold=["scn"]),
                                  hide_index=True, width="stretch", height=420, column_config=cfg,
                                  on_select="rerun", selection_mode="single-row", key="chg_table")
                sel = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
                if sel:
                    r = view.iloc[sel[0]]
                    if slot.button(C.L("btn_open_customer", name=r["name"]), type="primary",
                                   icon=":material/person_search:"):
                        ss.customer = r["code"]
                        st.switch_page(C.PAGE_FILES["customer"])

    # --- Sensitivity -------------------------------------------------------
    with tab_s:
        # param -> (label key, default from, default to, step, UI -> param, param -> UI, value format)
        SENS: dict[str, tuple] = {
            "multiplier": ("p_multiplier", 1.0, 3.0, 0.25, float, float, lambda v: LG.coef(v, lg)),
            "buffer": ("p_buffer_pct", 0.0, 30.0, 5.0, lambda v: v / 100, lambda v: v * 100,
                       lambda v: LG.pct(v, lg)),
            "coef_caution": ("p_coef_caution", 0.0, 1.0, 0.05, float, float, lambda v: LG.coef(v, lg)),
            "coef_not_in_cerved": ("p_coef_not_in_cerved", 0.0, 1.0, 0.05, float, float, lambda v: LG.coef(v, lg)),
            "coef_max_caution": ("p_coef_max_caution", 0.0, 1.0, 0.05, float, float, lambda v: LG.coef(v, lg)),
            "coef_reliable": ("p_coef_reliable", 0.0, 1.0, 0.05, float, float, lambda v: LG.coef(v, lg)),
            "min_limit": ("p_min_limit", 0.0, 20000.0 * SF, max(1.0, 1000.0 * SF), float, float, lambda v: LG.num(v, lg)),
            "min_days": ("p_days_min", 0.0, 40.0, 5.0, int, float, lambda v: LG.days(v, lg)),
            "cap_extra_days": ("p_days_over_terms", 0.0, 60.0, 5.0, int, float, lambda v: LG.days(v, lg)),
            "fallback_days": ("p_days_default", 15.0, 90.0, 5.0, int, float, lambda v: LG.days(v, lg)),
        }
        if p.behaviour_enabled:   # the bonus / malus values only move the results when the option is on
            SENS.update({
                "behaviour_bonus_max": ("p_beh_bonus", 0.0, 10.0, 1.0, lambda v: v / 100, lambda v: v * 100,
                                        lambda v: LG.pct(v, lg)),
                "behaviour_malus_max": ("p_beh_malus", 0.0, 20.0, 1.0, lambda v: v / 100, lambda v: v * 100,
                                        lambda v: LG.pct(v, lg)),
                "behaviour_tolerance_days": ("p_beh_tol", 0.0, 20.0, 1.0, int, float, lambda v: LG.days(v, lg)),
                "behaviour_full_malus_days": ("p_beh_full", 10.0, 90.0, 5.0, int, float, lambda v: LG.days(v, lg)),
            })
        if p.age_bands_enabled:   # customer-age thresholds (v3.2)
            SENS.update({
                "new_customer_months": ("p_age_new", 0.0, 6.0, 1.0, int, float, lambda v: LG.num(v, lg)),
                "consolidated_months": ("p_age_consolidated", 6.0, 24.0, 2.0, int, float, lambda v: LG.num(v, lg)),
            })
        if p.behaviour_enabled:
            SENS["behaviour_min_invoices"] = ("p_beh_min_inv", 0.0, 8.0, 1.0, int, float, lambda v: LG.num(v, lg))
        if ss.get("sens_key") not in SENS:
            ss.pop("sens_key", None)
        s1, s2, s3, s4 = st.columns([3, 2, 2, 1.4], vertical_alignment="bottom")
        sk = s1.selectbox(C.L("sens_param"), list(SENS), format_func=lambda k: tl(SENS[k][0]), key="sens_key")
        lab_key, d_from, d_to, stp, to_p, to_ui, fmt_v = SENS[sk]
        fa, fb = ss.get(f"sens_from_{sk}", d_from), ss.get(f"sens_to_{sk}", d_to)
        a = s2.number_input(f"{C.L('sens_from')}: {fmt_v(to_p(fa))}", value=d_from, step=stp, key=f"sens_from_{sk}")
        b = s3.number_input(f"{C.L('sens_to')}: {fmt_v(to_p(fb))}", value=d_to, step=stp, key=f"sens_to_{sk}")
        run = s4.button(C.L("btn_run_sens"), type="primary", key="sens_run", width="stretch")
        if run:
            if a >= b:
                st.error(C.L("sens_range_err"))
            else:
                vals = [to_p(round(float(x), 4)) for x in np.linspace(a, b, 9)]
                if to_p is int:
                    vals = list(dict.fromkeys(vals))
                bad = [v for v in vals if p.replace(**{sk: v}).validate()]
                if bad:
                    st.error("; ".join(p.replace(**{sk: bad[0]}).validate()))
                else:
                    with st.spinner(C.L("sens_running")):
                        df = sensitivity(data, p, sk, vals, kpi_keys=["limits_proposed_active", "over_new_n",
                                                                     "excess_new", "zero_with_turnover_n_active"])
                    ss.sens = {"key": sk, "df": df, "pjson": p.to_json(), "from": a, "to": b}
        sens = ss.get("sens")
        if not sens or sens["key"] != sk:
            st.info(C.L("sens_empty"), icon=":material/info:")
        else:
            if sens["pjson"] != p.to_json():
                st.caption(C.L("sens_stale"))
            lab_key, _f, _t, _s, _tp, _tu, fmt_v = SENS[sens["key"]]
            df = sens["df"].copy()
            cur_v = getattr(Params.from_json(sens["pjson"]), sens["key"])
            pname = C.L(lab_key)
            st.caption(C.L("sens_caption", param=pname, a=fmt_v(df["value"].iloc[0]), b=fmt_v(df["value"].iloc[-1])))
            df["x"] = df["value"].astype(float)
            df["label_x"] = df["value"].map(fmt_v)
            df["lim_m"] = df["limits_proposed_active"] / 1e6
            df["lim_lab"] = df["lim_m"].map(lambda v: LG.num(v, lg, 2))
            df["over_lab"] = df["over_new_n"].map(lambda v: LG.num(v, lg))
            ref_lim = ks["limits_current_active"] / 1e6
            ref_over = ks["over_current_n"]

            def axis(fmt: str) -> alt.Axis:
                """Axis labels in the language's number format (Vega formats in English)."""
                if lg != "it":
                    return alt.Axis(format=fmt)
                return alt.Axis(labelExpr=f"replace(replace(replace(format(datum.value, '{fmt}'), /,/g, '#'), "
                                          "/[.]/g, ','), /#/g, '.')")

            xfmt = ",.0%" if sens["key"] in ("buffer", "behaviour_bonus_max", "behaviour_malus_max") else (",.2~f" if df["x"].max() < 100 else ",.0f")

            def line(ycol: str, ylab: str, title: str, ref: float) -> alt.LayerChart:
                xenc = alt.X("x:Q", title=pname, scale=alt.Scale(zero=False), axis=axis(xfmt))
                yfmt = ",.1f" if ycol == "lim_m" else ",.0f"
                base_c = alt.Chart(df).encode(x=xenc, y=alt.Y(f"{ycol}:Q", title=None, scale=alt.Scale(zero=False),
                                                                 axis=axis(yfmt)))
                ln = base_c.mark_line(color="#1F4E79", point=alt.OverlayMarkDef(color="#1F4E79", size=60)).encode(
                    tooltip=[alt.Tooltip("label_x:N", title=pname), alt.Tooltip(f"{ylab}:N", title=title)])
                txt = base_c.mark_text(dy=-12, fontSize=13).encode(text=f"{ylab}:N")
                vr = alt.Chart(pd.DataFrame({"x": [float(cur_v)], "t": [C.L("sens_now")]})).mark_rule(
                    strokeDash=[6, 4], color="#1F4E79").encode(x="x:Q", tooltip=alt.Tooltip("t:N", title=" "))
                hr = alt.Chart(pd.DataFrame({"y": [ref], "t": [C.L("sens_cur_limits")]})).mark_rule(
                    strokeDash=[4, 4], color="#9AA5B1").encode(y="y:Q", tooltip=alt.Tooltip("t:N", title=" "))
                return (ln + txt + vr + hr).properties(height=300)

            # titles as text above the charts: a Vega title longer than the chart is cut
            g1, g2 = st.columns(2)
            g1.markdown(f"**{C.L('sens_chart_limits')}**")
            g1.altair_chart(line("lim_m", "lim_lab", C.L("sens_chart_limits"), ref_lim)
                            .configure_axis(labelFontSize=14, titleFontSize=15))
            g2.markdown(f"**{C.L('sens_chart_over')}**")
            g2.altair_chart(line("over_new_n", "over_lab", C.L("sens_chart_over"), ref_over)
                            .configure_axis(labelFontSize=14, titleFontSize=15))
            st.caption(C.L("sens_legend"))
            tbl = pd.DataFrame({C.L("sens_col_value"): df["label_x"], C.L("sens_col_limits"): df["limits_proposed_active"],
                                C.L("sens_col_over"): df["over_new_n"], C.L("sens_col_excess"): df["excess_new"],
                                C.L("sens_col_zero"): df["zero_with_turnover_n_active"]})
            is_cur = np.isclose(df["x"].to_numpy(), float(cur_v))
            sty = C.styler(tbl, [C.L("sens_col_limits"), C.L("sens_col_excess")],
                           counts=[C.L("sens_col_over"), C.L("sens_col_zero")])
            sty = sty.apply(lambda r: ["font-weight: bold" if is_cur[r.name] else "" for _ in r], axis=1)
            st.dataframe(sty, hide_index=True, width="stretch")

    # --- Scenarios ---------------------------------------------------------
    with tab_c:
        ws = C.workspace_dir()
        flash = ss.pop("_flash", None)
        if flash:
            kind, text = flash
            if kind == "toast":
                st.toast(text, icon=":material/check:")
            elif kind == "error":
                st.error(text)
            else:
                st.caption(text)
        flash2 = ss.pop("_flash2", None)
        if flash2:
            st.caption(flash2)

        def _save() -> None:
            name = (ss.get("scn_name_in") or "").strip()
            if not name:
                ss._flash = ("error", C.L("scn_name_empty"))
                return
            if SC.exists(ws, name) and not ss.get("scn_over"):
                ss._flash = ("error", C.L("scn_exists"))
                return
            SC.save(ws, name, C.params())
            ss.scn_name, ss.scn_json = name, C.params().to_json()
            ss._flash = ("toast", C.L("scn_saved", name=name))

        c1, c3 = st.columns([3, 1.2], vertical_alignment="bottom")
        c1.text_input(C.L("scn_name"), placeholder=C.L("scn_name_ph"), key="scn_name_in")
        c3.button(C.L("btn_save"), on_click=_save, type="primary", icon=":material/save:", key="scn_save",
                  width="stretch")
        st.checkbox(C.L("scn_overwrite"), key="scn_over")

        saved = SC.list_all(ws)
        cur_json = p.to_json()
        act = f" {C.L('scn_active')}"
        rows = [{"name": C.L("scn_v3") + (act if cur_json == base.to_json() else ""),
                 "lim": kb["limits_proposed_active"], "pos": kb["over_new_positive_n"], "over": kb["over_new_n"],
                 "exc": kb["excess_new"], "zero": kb["zero_with_turnover_n_active"], "appr": kb["approval_n"],
                 "diff": ""},
                {"name": C.L("scn_current_limits"),
                 "lim": kb["limits_current_active"], "pos": kb["over_current_positive_n"], "over": kb["over_current_n"],
                 "exc": kb["excess_current"], "zero": kb["zero_with_turnover_current_n"], "appr": np.nan,
                 "diff": C.L("scn_current_limits_diff")}]
        for s in saved:
            k = C.simulate(data, key, s["params"])["kpi"]
            rows.append({"name": s["name"] + (act if s["params"].to_json() == cur_json else ""),
                         "lim": k["limits_proposed_active"], "pos": k["over_new_positive_n"],
                         "over": k["over_new_n"], "exc": k["excess_new"], "zero": k["zero_with_turnover_n_active"],
                         "appr": k["approval_n"], "diff": LG.short_changes(s["params"], lg)})
        tbl = pd.DataFrame(rows)
        cc = st.column_config
        # numbers first, the long "what differs" text last
        st.dataframe(C.styler(tbl, ["lim", "exc"], counts=["pos", "over", "zero", "appr"]), hide_index=True,
                     width="stretch",
                     column_config={"name": cc.TextColumn(C.L("scn_col_name"), width=150),
                                    "lim": cc.NumberColumn(C.L("scn_col_limits")),
                                    "pos": cc.NumberColumn(C.L("scn_col_over_pos")),
                                    "over": cc.NumberColumn(C.L("scn_col_over")),
                                    "exc": cc.NumberColumn(C.L("scn_col_excess")),
                                    "zero": cc.NumberColumn(C.L("scn_col_zero")),
                                    "appr": cc.NumberColumn(C.L("scn_col_approval")),
                                    "diff": cc.TextColumn(C.L("scn_col_diff"), width="large")})

        if not saved:
            st.info(C.L("scn_empty"), icon=":material/info:")
        else:
            files = [s["file"] for s in saved]
            by_file = {s["file"]: s for s in saved}
            if ss.get("scn_pick") not in files:
                ss.scn_pick = files[0]

            def _load() -> None:
                s = by_file.get(ss.scn_pick)
                if s:
                    C.set_params(s["params"], name=s["name"])
                    ss._flash = ("toast", C.L("scn_loaded", name=s["name"]))

            def _delete() -> None:
                s = by_file.get(ss.scn_pick)
                if s:
                    SC.delete(ws, s["file"])
                    ss._flash = ("toast", C.L("scn_deleted", name=s["name"]))

            st.selectbox(C.L("scn_pick"), files, key="scn_pick", format_func=lambda f: by_file[f]["name"])
            d2, d3, d4 = st.columns(3)
            d2.button(C.L("btn_load"), on_click=_load, key="scn_load", width="stretch", icon=":material/upload:")
            d3.button(C.L("btn_delete"), on_click=_delete, key="scn_delete", width="stretch",
                      icon=":material/delete:")
            d4.download_button(C.L("btn_export_json"), data=SC.export_bytes(ws, ss.scn_pick),
                               file_name=ss.scn_pick, mime="application/json", key="scn_export",
                               icon=":material/download:", width="stretch")

        def _import() -> None:
            f = ss.get("scn_import_file")
            if f is None:
                return
            try:
                name, params_in, ignored = SC.parse(f.getvalue(), f.name.rsplit(".", 1)[0])
            except ValueError:
                ss._flash = ("error", C.L("scn_import_err"))
                return
            SC.save(ws, name, params_in)
            ss._flash = ("toast", C.L("scn_import_ok", name=name))
            if ignored:
                ss._flash2 = C.L("scn_import_ignored", list=", ".join(ignored))

        st.file_uploader(C.L("scn_import"), type=["json"], key="scn_import_file", on_change=_import)
        st.caption(C.L("scn_folder", path=str(ws)))
