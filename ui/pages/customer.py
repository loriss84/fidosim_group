"""Page "Cliente / Customer": how do we get to this limit? (UX.md section 4)

Layout (v3.3): header with badges, four tiles, the answer in two sentences, then four tabs:
calculation · Cerved, payments and checks · public balance sheet (ANAF) · invoices.
"""
from __future__ import annotations

import re

import altair as alt
import pandas as pd
import streamlit as st

from core import balance as BS
from core import texts as TX
from core.engine import (SCORE_CAUTION, SCORE_MAX, SCORE_RELIABLE, blocked_months, customer_invoices,
                         purchase_gap_effect, purchase_months)
from ui import common as C
from ui import logic as LG

ss = st.session_state
lg = C.lang()
data, key = C.get_data()
p = C.params()

C.page_header("cust", data)
if C.no_data(data):
    st.stop()
if p.age_bands_enabled:
    C.coverage_banner(data)

sim = C.simulate(data, key)
allc = sim["all"].sort_values(["exposure", "code"], ascending=[False, True]).reset_index(drop=True)
codes = allc["code"].tolist()
names = dict(zip(allc["code"], allc["name"].fillna("")))

# keep the picker in sync with a customer chosen on another page (Results / Lab row click)
if ss.get("customer") in names and ss.get("cust_sel") != ss.customer:
    ss.cust_sel = ss.customer
if ss.get("cust_sel") not in names:
    ss.cust_sel = codes[0]


def _on_pick() -> None:
    ss.customer = ss.cust_sel


st.selectbox(C.L("cust_pick"), codes, key="cust_sel", format_func=lambda c: f"{c} · {names.get(c, '')}",
             help=C.L("cust_pick_help"), on_change=_on_pick)
row = allc[allc["code"] == ss.cust_sel].iloc[0]


def box(title_key: str, rows: list[tuple[str, str]]) -> None:
    """Two-column label | value table; the box title is the header."""
    st.markdown(C.md_table([f"**{C.L(title_key)}**", ""], [list(r) for r in rows]))


cur, new, expo = float(row["current_limit"]), float(row["proposed_limit"]), float(row["exposure"])
cust_row = data.matched_customers(p.cerved_reject_vat_conflict)
cust_row = cust_row[cust_row["code"] == row["code"]]

# --- public balance sheet: read what is already known (session or saved on this PC), no network ---
if "bs_params" not in ss:
    ss.bs_params = BS.BalanceParams()
bp: BS.BalanceParams = ss.bs_params
ss.setdefault("bs_results", {})
bs_dir = C.workspace_dir() / "anaf"
_cv_vat = cust_row["cv_vat"].iloc[0] if len(cust_row) and "cv_vat" in cust_row else None
cui, cui_state = BS.cui_from_vat(row["vat"], _cv_vat)
bs_res = None
if cui is not None:
    bs_res = ss.bs_results.get(cui)
    if bs_res is None and (bs_dir / f"anaf_{cui}.json").exists():
        bs_res = ss.bs_results[cui] = BS.lookup(cui, cache_dir=bs_dir)


def _assessment(res: dict | None) -> BS.Assessment | None:
    if not res or res.get("status") != "ok":
        return None
    return BS.assess(res["values"], int(res["year"]), new, cur, row.get("turnover_12m"), bp=bp)


bs_a = _assessment(bs_res)
BS_STYLE = {"valid": (st.success, ":material/check_circle:", "green"),
            "valid_watch": (st.warning, ":material/visibility:", "orange"),
            "too_high": (st.error, ":material/cancel:", "red"),
            "zero_confirmed": (st.success, ":material/check_circle:", "green"),
            "zero_formula": (st.info, ":material/info:", "blue"),
            "na": (st.info, ":material/info:", "gray")}


def verdict_head(a: BS.Assessment, res: dict) -> str:
    """The one-sentence answer: is the proposed limit right for this company, and if not, what is."""
    eq = res["values"].get("equity")
    lim, cap, sug = LG.amt(new, lg), LG.amt(a.capacity, lg), LG.amt(a.suggested, lg)
    if a.verdict == "too_high":
        return C.L("bs_v_too_high_zero" if (a.capacity or 0) <= 0 and (eq or 0) <= 0 else "bs_v_too_high",
                   lim=lim, sug=sug)
    return C.L(f"bs_v_{a.verdict}", lim=lim, cap=cap)

# --- header: name, badges, identifiers -------------------------------------------------------
score = LG.score_label(row["score_bucket"], lg)
st.markdown(f"## {row['name']}")
badges: list[str] = []
if p.age_bands_enabled:   # customer-age badge (v3.2)
    if row["age_band"] == "NO_HISTORY":
        badges.append(f":gray-badge[{C.L('cust_age_badge_none')}]")
    else:
        color = {"NEW": "orange", "YOUNG": "blue", "CONSOLIDATED": "green"}.get(row["age_band"], "gray")
        src = TX.AGE_SOURCE_TEXTS.get(row["age_source"], {}).get(lg, "-") if isinstance(row["age_source"], str) else "-"
        badge_key = "cust_age_badge_min" if bool(row["age_censored"]) else "cust_age_badge"
        badges.append(f":{color}-badge[{C.L(badge_key, band=LG.age_label(row['age_band'], lg), months=TX.render('{x:dd}', lg, x=row['age_months']), src=src)}]")
s_color = {SCORE_RELIABLE: "green", SCORE_CAUTION: "orange", SCORE_MAX: "red"}.get(row["score_bucket"], "gray")
badges.append(f":{s_color}-badge[Cerved: {score}]")
if isinstance(row["risk_class"], str) and row["risk_class"]:
    badges.append(f":gray-badge[{C.L('cust_badge_class', cls=row['risk_class'])}]")
if row["is_exempt"]:
    badges.append(f":violet-badge[{C.L('cust_badge_exempt')}]")
elif row["is_special"]:
    badges.append(f":red-badge[{C.L('cust_badge_special')}]")
if bs_a is not None:
    b_color = {"valid": "green", "valid_watch": "orange", "too_high": "red", "zero_confirmed": "green"}.get(
        bs_a.verdict, "gray")
    badges.append(f":{b_color}-badge[{C.L('cust_badge_bs', year=bs_res['year'], v=C.L('bs_vs_' + bs_a.verdict))}]")
st.markdown(" ".join(badges))
st.caption(C.L("cust_ids", code=row["code"], vat=row["vat"] if isinstance(row["vat"], str) else "-"))

if row["is_intercompany"]:
    st.info(LG.reason_long(row, p, lg), icon=":material/lightbulb:")
    st.stop()

# --- tiles ---------------------------------------------------------------------------------------
t = st.columns(4)
t[0].metric(C.L("cust_t_cur"), LG.amt(cur, lg), border=True)
t[1].metric(C.L("cust_t_new"), LG.amt(new, lg),
            C.L("delta_vs_current_short", d=LG.signed(new - cur, lg) + " RON") if abs(new - cur) >= 0.5 else None,
            delta_color="off", border=True)
t[2].metric(C.L("cust_t_expo"), LG.amt(expo, lg), border=True)
over_new, over_cur = expo > new, expo > cur
with t[3]:
    # only customers in the order-check scope are checked; exempt / special are not
    if row["is_exempt"] or row["is_special"]:
        st.metric(C.L("cust_t_over"), C.L("cust_over_not_checked"), border=True)
        st.caption(C.L("cust_over_special_caption") if row["is_special"] else
                   C.L("cust_over_exempt_above" if over_new else "cust_over_exempt_within"))
    else:
        st.metric(C.L("cust_t_over"), C.L("yes" if over_new else "no"), border=True)
        st.caption(C.L("cust_t_over_caption", v=C.L("yes" if over_cur else "no")))

# --- the answer in two sentences ------------------------------------------------------------------
why = LG.why_change(row, p, lg)
if row["days_capped"]:
    why += " " + C.L("w_suffix_late", meas=LG.num(row["days_raw"], lg), days=LG.num(row["days_used"], lg),
                     over=LG.num(p.cap_extra_days, lg))
msg = LG.reason_long(row, p, lg) + "\n\n" + why
if row["is_exempt"]:
    msg += "\n\n" + C.L("r_EXEMPT_note", cls=row["risk_class"])
if row["reason_code"] in LG.ZERO_REASONS:
    st.warning(msg, icon=":material/block:")
else:
    st.info(msg, icon=":material/lightbulb:")
if bool(row["revenue_check_flag"]):
    st.warning(C.L("cust_new_warning", months=TX.render("{x:dd}", lg, x=row["months_active"])),
               icon=":material/storefront:")

# --- balance-sheet check strip: always visible, the button lives here ---------------------------------
with st.container(border=True):
    st.markdown(f":material/account_balance: **{C.L('bs_strip_title')}** · " + C.L("bs_strip_sub"))
    if cui is None:
        st.caption(C.L("bs_foreign" if cui_state == "foreign" else "bs_no_cui"))
    else:
        s1, s2 = st.columns([2, 1], vertical_alignment="center")
        with s1:
            if not bs_res:
                st.markdown(C.L("bs_strip_todo"))
            elif bs_res["status"] == "ok" and bs_a is not None:
                color = BS_STYLE[bs_a.verdict][2]
                st.markdown(f":{color}[**{verdict_head(bs_a, bs_res)}**]  \n" + C.L("bs_strip_details", year=bs_res["year"]))
            elif bs_res["status"] == "not_found":
                st.markdown(C.L("bs_not_found", cui=cui, years=", ".join(str(y) for y in bs_res.get("years_tried", []))))
            else:
                st.markdown(":red[" + C.L("bs_error", err=bs_res.get("error", "?"), url=bs_res.get("url", "")) + "]")
        with s2:
            if st.button(C.L("bs_btn_refresh" if bs_res else "bs_btn"), icon=":material/account_balance:",
                         key=f"bs_btn_{cui}", type="secondary" if bs_res else "primary", width="stretch"):
                with st.spinner(C.L("bs_spinner", cui=cui)):
                    ss.bs_results[cui] = BS.lookup(cui, cache_dir=bs_dir, refresh=True)
                st.rerun()   # badge, strip, tab and button label follow the new answer

tab_calc, tab_prof, tab_bs, tab_inv = st.tabs([
    ":material/calculate: " + C.L("cust_tab_calc"), ":material/fact_check: " + C.L("cust_tab_profile"),
    ":material/account_balance: " + C.L("cust_tab_balance"), ":material/receipt_long: " + C.L("cust_tab_invoices")])

# --- tab 1: calculation ----------------------------------------------------------------------------
def _mlabel(ts: pd.Timestamp) -> str:
    names = C.L("gap_months_short").split("|")
    return f"{names[ts.month - 1]} {ts.year % 100:02d}"


def _ranges(pm: pd.DataFrame) -> str:
    """Consecutive months without purchases: 'Dec 25 – May 26, Sep 26'."""
    out, run = [], []
    for _, r_ in pm.iterrows():
        if r_["amount"] <= 0:
            run.append(r_["month"])
        elif run:
            out.append(run)
            run = []
    if run:
        out.append(run)
    return ", ".join(_mlabel(x[0]) if len(x) == 1 else f"{_mlabel(x[0])} – {_mlabel(x[-1])}" for x in out)


pm = (purchase_months(data.ar, row["code"], C.ref_date(data), overdue_grace_days=int(p.behaviour_tolerance_days))
      if data.ar is not None else None)
gap = purchase_gap_effect(row, pm, p) if pm is not None else None

with tab_calc:
    if gap is not None:
        capped = gap["limit_alt"] <= gap["limit"]
        note = C.L("gap_note_capped" if capped else "gap_note", empty=gap["empty"], bought=gap["bought"],
                   ranges=_ranges(pm), m12=LG.amt(gap["monthly_12"], lg), mb=LG.amt(gap["monthly_bought"], lg),
                   alt=LG.amt(gap["limit_alt"], lg), lim=LG.amt(gap["limit"], lg))
        if expo > new and not (row["is_exempt"] or row["is_special"]):
            note += " " + C.L("gap_note_expo", expo=LG.amt(expo, lg))
        st.warning(note + "\n\n" + C.L("gap_note_tail"), icon=":material/event_busy:")
    rows = LG.step_rows(row, p, lg)
    st.markdown(C.md_table([C.L("st_col_n"), C.L("st_col_step"), C.L("st_col_calc"), C.L("st_col_ron")],
                           [[r["n"], r["step"], r["calc"], r["ron"]] for r in rows], align="lllr", bold_last=True))
    sent = [C.L("expo_sentence", expo=LG.amt(expo, lg), bal=LG.num(row["balance"], lg),
                ord=LG.num(row["ordered"], lg), dlv=LG.num(row["delivered"], lg))]
    if row["is_exempt"]:
        sent.append(C.L("expo_over_monitor", amt=LG.amt(expo - new, lg)) if over_new
                    else C.L("expo_ok_monitor", amt=LG.amt(new - expo, lg)))
        sent.append(C.L("expo_exempt"))
    elif row["is_special"]:
        sent.append(C.L("expo_special"))
    else:
        sent.append(C.L("expo_over_new", amt=LG.amt(expo - new, lg)) if over_new
                    else C.L("expo_ok_new", amt=LG.amt(new - expo, lg)))
        sent.append(C.L("expo_cur_over", cur=LG.amt(cur, lg), amt=LG.amt(expo - cur, lg)) if over_cur
                    else C.L("expo_cur_ok", cur=LG.amt(cur, lg)))
    st.markdown(" ".join(sent))
    if pm is not None and not pm.empty and (float(pm["amount"].sum()) > 0 or float(pm["peak_open"].max()) > 0):
        st.markdown(f"##### {C.L('gap_chart_title')}")
        ref = C.ref_date(data)
        b_new, b_cur = blocked_months(pm, new), blocked_months(pm, cur)
        cats = []
        for bn, bc in zip(b_new, b_cur):
            cats.append("both" if bn and bc else "new" if bn else "cur" if bc else "ok")
        lab = {k: C.L("blk_cat_" + k) for k in ("ok", "new", "both", "cur")}
        cd = pd.DataFrame({
            "m": [_mlabel(m_) + ("*" if part else "") for m_, part in zip(pm["month"], pm["partial"])],
            "amount": pm["amount"].round(0), "peak": pm["peak_open"].round(0), "od": pm["peak_overdue"].round(0),
            "cat": [lab[c_] for c_ in cats],
            "period": [f"{LG.date_str(a_)} – {LG.date_str(b_)}" for a_, b_ in zip(pm["month"], pm["end"])]})
        order = cd["m"].tolist()
        x = alt.X("m:N", sort=order, title=None, axis=alt.Axis(labelAngle=0))
        color = alt.Color("cat:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=0, columns=2, labelFontSize=13),
                          scale=alt.Scale(domain=[lab["ok"], lab["new"], lab["both"], lab["cur"]],
                                          range=["#0F4881", "#E07B00", "#C62828", "#7B1FA2"]))
        tips = [alt.Tooltip("period:N", title=C.L("gap_tt_period")),
                alt.Tooltip("amount:Q", title=C.L("blk_tt_amount"), format=",.0f"),
                alt.Tooltip("peak:Q", title=C.L("blk_tt_peak"), format=",.0f"),
                alt.Tooltip("od:Q", title=C.L("blk_tt_od", d=int(p.behaviour_tolerance_days)), format=",.0f"),
                alt.Tooltip("cat:N", title=C.L("blk_tt_cat"))]
        bars = alt.Chart(cd).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, opacity=0.85).encode(
            x=x, y=alt.Y("amount:Q", title="RON", axis=alt.Axis(format="~s")), color=color, tooltip=tips)
        line = alt.Chart(cd).mark_line(color="#1B2430", strokeWidth=2, point=alt.OverlayMarkDef(
            color="#1B2430", size=40)).encode(x=x, y="peak:Q", tooltip=tips)
        od_line = alt.Chart(cd).mark_line(color="#C62828", strokeWidth=2, point=alt.OverlayMarkDef(
            color="#C62828", size=30, shape="square")).encode(x=x, y="od:Q", tooltip=tips)
        lim_df = pd.DataFrame({"y": [cur, new], "who": [C.L("blk_line_cur", v=LG.amt(cur, lg)),
                                                         C.L("blk_line_new", v=LG.amt(new, lg))],
                               "c": ["#7A7A7A", "#E07B00"], "m": [order[0], order[0]]})
        rules = alt.Chart(lim_df).mark_rule(strokeDash=[6, 4], size=2).encode(
            y="y:Q", color=alt.Color("c:N", scale=None))
        tags = alt.Chart(lim_df).mark_text(align="left", dx=-30, dy=-8, fontSize=12, fontWeight="bold").encode(
            x=alt.X("m:N", sort=order), y="y:Q", text="who:N", color=alt.Color("c:N", scale=None))
        st.altair_chart(alt.layer(bars, line, od_line, rules, tags).resolve_scale(color="independent").properties(height=320),
                        width="stretch")
        mlist = lambda flags: ", ".join(o_ for o_, f_ in zip(order, flags) if f_)  # noqa: E731
        n_new, n_cur = sum(b_new), sum(b_cur)
        lines = [C.L("blk_sum_new_yes", v=LG.amt(new, lg), n=n_new, m=mlist(b_new)) if n_new
                 else C.L("blk_sum_new_no", v=LG.amt(new, lg)),
                 C.L("blk_sum_cur_yes", v=LG.amt(cur, lg), n=n_cur, m=mlist(b_cur)) if n_cur
                 else C.L("blk_sum_cur_no", v=LG.amt(cur, lg))]
        od_max = float(pm["peak_overdue"].max())
        lines.append(C.L("blk_od_yes", d=int(p.behaviour_tolerance_days), v=LG.amt(od_max, lg),
                         m=mlist([x_ >= od_max - 0.005 and x_ > 0 for x_ in pm["peak_overdue"]]))
                     if od_max > 0.005 else C.L("blk_od_no", d=int(p.behaviour_tolerance_days)))
        if row["is_exempt"]:
            lines.append(C.L("blk_exempt"))
        elif row["is_special"]:
            lines.append(C.L("blk_special"))
        st.markdown("  \n".join(lines))
        st.caption(C.L("blk_caption", ref=LG.date_str(ref), d=int(p.behaviour_tolerance_days),
                       terms=LG.num(row["days_terms"], lg)))


# --- tab 2: Cerved, payment days, checks ------------------------------------------------------------
with tab_prof:
    left, right = st.columns(2, gap="large")
    with left:
        conflict = None
        if bool(row["vat_conflict"]) and len(cust_row):
            cr = cust_row.iloc[0]
            conflict = C.L("cv_vat_conflict", code=row["code"],
                           cv_name=cr["conflict_cv_name"] if isinstance(cr["conflict_cv_name"], str) else "?",
                           cv_vat=cr["conflict_cv_vat"] if isinstance(cr["conflict_cv_vat"], str) else "?")
        if not row["in_cerved"]:
            box("box_cerved", [(C.L("cv_not_found"), "")])
        else:
            lim_unit = LG.whole_ron(row["cerved_limit_ron"])   # whole RON, as the proposed limit uses it
            if row["cerved_currency"] == "EUR" and pd.notna(row["cerved_limit_orig"]):
                lim = C.L("cv_limit_eur", eur=LG.num(row["cerved_limit_orig"], lg),
                          ron=LG.amt(lim_unit, lg), rate=LG.param_value("eur_ron", p.eur_ron, lg))
            else:
                lim = LG.amt(lim_unit, lg)
            box("box_cerved", [(C.L("cv_score"), score), (C.L("cv_limit"), lim),
                               (C.L("cv_class"), LG.num(row["reliability_class"], lg)),
                               (C.L("cv_turnover"), LG.amt(row["cerved_turnover"], lg)),
                               (C.L("cv_match"), C.L("cv_match_code" if row["match_method"] == "code" else "cv_match_vat"))])
            if row["vat_differs"]:
                cv_vat = cust_row["cv_vat"]
                st.caption(C.L("cv_vat_differs", vat=cv_vat.iloc[0] if len(cv_vat) else "-"))
        if conflict:
            st.caption(conflict)
        thr = LG.pct(p.plausibility_threshold, lg)
        ratio = row["plausibility_ratio"]
        if pd.isna(ratio):
            plaus = C.L("ck_plaus_na")
        else:
            plaus = C.L("ck_plaus_review" if row["plausibility_flag"] else "ck_plaus_ok", pct=LG.pct(ratio, lg, 1), thr=thr)
        if cur <= 0 and new <= 0:
            chg = C.L("ck_change_none")
        elif cur <= 0:
            chg = C.L("ck_change_new")
        else:
            chg = f"{LG.signed(new - cur, lg)} RON ({LG.signed_pct(row['diff_pct'], lg)})"
        athr = LG.pct(p.approval_threshold, lg)
        tier = C.L("ck_tier_na") if new <= 0 else C.L("ck_tier_val", t=int(row["tier"]), ron=LG.amt(new, lg),
                                                      eur=LG.num(row["proposed_limit_eur"], lg))
        box("box_checks", [(C.L("ck_plaus"), plaus), (C.L("ck_change"), chg),
                           (C.L("ck_approval"), C.L("ck_approval_yes" if row["approval_needed"] else "ck_approval_no",
                                                    thr=athr, amt=LG.amt(p.approval_min_change_ron, lg))),
                           (C.L("ck_tier"), tier)])
    with right:
        day_rows = [(C.L("pd_measured"), LG.days(row["days_measured"], lg)),
                    (C.L("pd_terms"), LG.days(row["days_terms"], lg)),
                    (C.L("pd_used"), LG.days(row["days_used"], lg)),
                    (C.L("pd_invoices"), LG.num(row["n_invoices"], lg))]
        if p.age_bands_enabled or p.behaviour_min_invoices > 0:   # customer age (v3.2)
            mo = lambda x: "-" if pd.isna(x) else TX.render("{x:dd}", lg, x=x) + " " + C.L("months_unit")  # noqa: E731
            if data.md105 is not None:
                day_rows.append((C.L("pd_opened"), LG.date_str(row["opened_date"])))
            day_rows += [(C.L("pd_first_invoice"), LG.date_str(row["first_invoice_date"])),
                         (C.L("pd_age"), (C.L("pd_age_min", months=mo(row["age_months"])) if bool(row["age_censored"])
                                          else mo(row["age_months"])) + (f" · {LG.age_label(row['age_band'], lg)}"
                                                                  if p.age_bands_enabled else "")),
                         (C.L("pd_months_active"), mo(row["months_active"])),
                         (C.L("pd_inv_due"), LG.num(row["behaviour_invoices_n"], lg))]
        if p.behaviour_enabled:   # payment bonus / malus: delay = measured - terms, and what it gives
            delay = row["delay_days"]
            day_rows.append((C.L("pd_delay"), "-" if pd.isna(delay) else
                             TX.render("{x:sdd}", lg, x=delay) + " " + C.L("days_unit")))
            day_rows.append((C.L("pd_behaviour"), f"{C.L('beh_' + str(row['behaviour_band']))} "
                             f"({TX.render('{x:spct}', lg, x=row['behaviour_pct'])})"))
        box("box_days", day_rows)
        if p.m1_days_basis == "contractual":
            st.caption(C.L("pd_basis_contract", days=LG.num(row["days_used"], lg)))
        elif row["days_capped"]:
            st.caption(C.L("days_capped", days=LG.num(row["days_used"], lg), meas=LG.num(row["days_raw"], lg),
                           over=LG.num(p.cap_extra_days, lg)))
        elif row["days_min_applied"]:
            st.caption(C.L("days_floored", days=LG.num(row["days_used"], lg)))


# --- tab 3: public balance sheet (ANAF), second opinion in plain words --------------------------------
def _x(v: float | None, d: int = 1) -> str:
    return "-" if v is None else TX.fmt_amount(float(v), lg, d)


def _card(col, level: str, question: str, headline: str, text: str) -> None:
    """One plain-language reading: coloured dot + question, the key figure, one sentence."""
    color = {"good": "green", "watch": "orange", "bad": "red", "info": "gray"}[level]
    with col.container(border=True):
        st.markdown(f":{color}[●] **{question}**")
        st.markdown(f"#### :{color}[{headline}]" if level != "info" else f"#### {headline}",
                    help=None if level == "info" else C.L("bs_lvl_" + level))
        st.markdown(text)


def _same_name(a: str, b: str) -> bool:
    strip = lambda s: re.sub(r"\b(SC|S\.?C\.?|SRL|S\.?R\.?L\.?|SA|S\.?A\.?)\b|[^A-Z0-9]", "", str(s).upper())  # noqa: E731
    n1, n2 = strip(a), strip(b)
    return not n1 or not n2 or n1[:6] == n2[:6] or n1 in n2 or n2 in n1


def _show_balance(res: dict, a: BS.Assessment) -> None:
    v, yr = res["values"], int(res["year"])
    r = a.ratios
    eq = v.get("equity")
    lim, cap, sug = LG.amt(new, lg), LG.amt(a.capacity, lg), LG.amt(a.suggested, lg)
    # 1) the verdict -------------------------------------------------------------------------------
    head = verdict_head(a, res)
    why: list[str] = []
    if eq is not None and eq <= 0:
        why.append(C.L("bs_why_neg", eq=LG.amt(eq, lg)))
    elif eq is not None and a.share_used is not None:
        why.append(C.L("bs_why_capacity", share=LG.pct(a.share_used, lg), eq=LG.amt(eq, lg), cap=cap))
        if a.weaknesses:
            why.append(C.L("bs_why_weak", share=LG.pct(a.share_used, lg), full=LG.pct(bp.equity_share, lg),
                           list="; ".join(C.L("bs_weak_" + w) for w in a.weaknesses)))
    if a.old:
        why.append(C.L("bs_old", year=yr, months=a.age_months))
    body = f"**{head}**" + ("\n\n" + "\n\n".join(why) if why else "")
    show, icon, _c = BS_STYLE[a.verdict]
    show(body, icon=icon)
    if a.verdict != "na":
        k = st.columns(4)
        k[0].metric(C.L("bs_k_proposed"), lim, border=True)
        k[1].metric(C.L("bs_k_capacity"), cap, border=True)
        d = (a.suggested or 0) - new
        k[2].metric(C.L("bs_k_suggested"), sug, (LG.signed(d, lg) + " RON") if abs(d) >= 0.5 else None,
                    delta_color="normal", border=True)
        k[3].metric(C.L("bs_k_current"), LG.amt(cur, lg), border=True)
        if r["current_on_equity"] is not None and cur > 0:
            k[3].caption(C.L("bs_k_current_help", pct=LG.pct(r["current_on_equity"], lg, 1)))
    # 2) the balance sheet in plain words ----------------------------------------------------------
    st.markdown(f"##### {C.L('bs_read_title')}")
    g1, g2, g3 = st.columns(3)
    to, emp = v.get("turnover"), v.get("employees")
    _card(g1, "info", C.L("bs_q_size"), LG.big(to, lg),
          C.L("bs_a_size", to=LG.big(to, lg), emp=LG.num(emp, lg)) if emp else C.L("bs_a_size_noemp", to=LG.big(to, lg)))
    net = r["net_result"]
    if net is None:
        _card(g2, "info", C.L("bs_q_profit"), "-", C.L("bs_a_profit_na"))
    else:
        per100 = _x(abs(net) / to * 100, 1) + " RON" if to else "-"
        _card(g2, "good" if net >= 0 else "bad", C.L("bs_q_profit"), LG.signed_big(net, lg, abs(net) >= 1e6),
              C.L("bs_a_profit" if net >= 0 else "bs_a_loss", net=LG.big(abs(net), lg), m=per100))
    if eq is None:
        _card(g3, "info", C.L("bs_q_equity"), "-", C.L("bs_v_na"))
    else:
        _card(g3, "good" if eq > 0 else "bad", C.L("bs_q_equity"), LG.big(eq, lg),
              C.L("bs_a_equity", eq=LG.big(eq, lg)) if eq > 0 else C.L("bs_a_equity_neg", eq=LG.big(abs(eq), lg)))
    h1, h2, h3 = st.columns(3)
    debts, lev, liq = v.get("debts"), r["debt_to_equity"], r["liquidity"]
    if lev is None:
        _card(h1, "bad" if (eq or 0) <= 0 else "info", C.L("bs_q_debt"), LG.big(debts, lg),
              C.L("bs_a_debt_neg", debts=LG.big(debts, lg)))
    else:
        _card(h1, "watch" if lev > bp.max_debt_to_equity else "good", C.L("bs_q_debt"), f"{_x(lev)} : 1",
              C.L("bs_a_debt", debts=LG.big(debts, lg), x=_x(lev), max=_x(bp.max_debt_to_equity)))
    _card(h2, "info" if liq is None else ("watch" if liq < bp.min_liquidity else "good"), C.L("bs_q_liq"),
          "-" if liq is None else f"{_x(liq, 2)} : 1",
          C.L("bs_a_liq", x=_x(liq, 2), min=_x(bp.min_liquidity)))
    sh = r["siad_share"]
    _card(h3, "info", C.L("bs_q_siad"), LG.pct(sh, lg, 1),
          C.L("bs_a_siad", pct=LG.pct(sh, lg, 1)) if sh is not None else C.L("bs_a_siad_na"))
    # 3) source and technical details ---------------------------------------------------------------
    st.caption(C.L("bs_source", name=res.get("name") or "-", cui=res["cui"], year=yr,
                   desc=res.get("caen_desc") or "-", at=str(res.get("fetched_at", "")).replace("T", " ")[:16],
                   url=res.get("url", "")))
    if not _same_name(row["name"], res.get("name", "")):
        st.warning(C.L("bs_name_differs", name=res.get("name", "")), icon=":material/badge:")
    with st.expander(C.L("bs_tech"), icon=":material/table_chart:"):
        t1, t2 = st.columns(2)
        t1.markdown(C.md_table([C.L("bs_box_values"), " "], [
            [C.L("bs_turnover"), LG.num(to, lg)],
            [C.L("bs_net"), "-" if net is None else LG.signed(net, lg)],
            [C.L("bs_equity"), LG.num(eq, lg)], [C.L("bs_debts"), LG.num(debts, lg)],
            [C.L("bs_current"), LG.num(v.get("current_assets"), lg)],
            [C.L("bs_receivables"), LG.num(v.get("receivables"), lg)],
            [C.L("bs_inventory"), LG.num(v.get("inventory"), lg)], [C.L("bs_cash"), LG.num(v.get("cash"), lg)],
            [C.L("bs_employees"), LG.num(emp, lg)]], align="lr"))
        t2.markdown(C.md_table([C.L("bs_box_ratios"), " "], [
            [C.L("bs_r_margin"), LG.pct(r["net_margin"], lg, 1)], [C.L("bs_r_leverage"), _x(lev)],
            [C.L("bs_r_liquidity"), _x(liq, 2)], [C.L("bs_r_limit"), LG.pct(r["limit_on_equity"], lg, 1)],
            [C.L("bs_r_current"), LG.pct(r["current_on_equity"], lg, 1)],
            [C.L("bs_r_siad"), LG.pct(sh, lg, 1)]], align="lr"))
        st.markdown(f"**{C.L('bs_raw')}**")
        st.dataframe(pd.DataFrame(res.get("raw", []), columns=[C.L("bs_raw_code"), C.L("bs_raw_desc"),
                                                               C.L("bs_raw_val")]),
                     hide_index=True, width="stretch")


with tab_bs:
    st.caption(C.L("bs_intro"))
    if cui is None:
        st.info(C.L("bs_foreign" if cui_state == "foreign" else "bs_no_cui"), icon=":material/public_off:")
    else:
        if not bs_res:
            st.info(C.L("bs_tab_todo"), icon=":material/arrow_upward:")
        elif bs_res["status"] == "error":
            st.error(C.L("bs_error", err=bs_res.get("error", "?"), url=bs_res.get("url", "")),
                     icon=":material/cloud_off:")
        elif bs_res["status"] == "not_found":
            st.info(C.L("bs_not_found", cui=cui, years=", ".join(str(y) for y in bs_res.get("years_tried", []))),
                    icon=":material/search_off:")
        else:
            _show_balance(bs_res, bs_a)
        with st.expander(C.L("bs_rules"), icon=":material/tune:"):
            st.caption(C.L("bs_rules_caption"))
            q = st.columns(5)
            sh_ = q[0].number_input(C.L("bs_p_share"), 1, 100, int(round(bp.equity_share * 100)), 1, key="bs_p_share")
            wk_ = q[1].number_input(C.L("bs_p_weak"), 1, 100, int(round(bp.weak_equity_share * 100)), 1, key="bs_p_weak")
            lv_ = q[2].number_input(C.L("bs_p_lev"), 0.5, 50.0, float(bp.max_debt_to_equity), 0.5, key="bs_p_lev")
            lq_ = q[3].number_input(C.L("bs_p_liq"), 0.0, 5.0, float(bp.min_liquidity), 0.1, key="bs_p_liq")
            ag_ = q[4].number_input(C.L("bs_p_age"), 6, 60, int(bp.max_age_months), 1, key="bs_p_age")
            newp = BS.BalanceParams(sh_ / 100, min(wk_, sh_) / 100, lv_, lq_, int(ag_))
            if newp != bp:
                ss.bs_params = newp
                st.rerun()

# --- tab 4: invoices ----------------------------------------------------------------------------------
with tab_inv:
    if data.ar is None:
        st.caption(C.L("cust_no_invoices"))
    else:
        inv = customer_invoices(data.ar, row["code"], C.ref_date(data), p.window_months)
        if inv.empty:
            st.caption(C.L("cust_no_invoices"))
        else:
            st.caption(C.L("cust_invoices_caption", n=LG.num(len(inv), lg)))
            show = pd.DataFrame({
                C.L("inv_date"): inv["invoice_date"].map(LG.date_str),
                C.L("inv_due"): inv["due_date"].map(LG.date_str),
                C.L("inv_closed"): [C.L("inv_open") if o else LG.date_str(d)
                                    for o, d in zip(inv["is_open"], inv["closed_date"])],
                C.L("inv_amount"): inv["amount"].values,
                C.L("inv_days"): inv["days"].astype(int).values})
            st.dataframe(C.styler(show, [C.L("inv_amount")], counts=[C.L("inv_days")]), hide_index=True,
                         width="stretch", height=420)
