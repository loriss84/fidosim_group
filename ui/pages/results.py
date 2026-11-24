"""Page "Risultati / Results": what changes with the new formula? (UX.md section 3)"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from core.kpi import age_breakdown, score_breakdown
from core import texts as TX
from ui import common as C
from ui import logic as LG

BLUE, GREY, LIGHT_BLUE, ORANGE = "#1F4E79", "#9AA5B1", "#2E75B6", "#D9822B"

ss = st.session_state
lg = C.lang()


def tl(k: str) -> str:
    """Text in this run's language without touching session state (safe in format_func)."""
    return TX.T(k, lg)

data, key = C.get_data()
p = C.params()

C.page_header("res", data)
if C.no_data(data):
    st.stop()
if p.age_bands_enabled:
    C.coverage_banner(data)

with st.spinner(C.L("calculating")):
    sim = C.simulate(data, key)
res, k = sim["res"], sim["kpi"]
has_cerved = data.cerved is not None
has_current = bool((res["current_limit"] > 0).any())


def delta_cur(d: float, cur_txt: str, in_mln: bool = False, money: bool = False) -> str | None:
    if not has_current:
        return None
    if money:  # amounts: short delta (the current amount is in the help text)
        return C.L("delta_vs_current_short", d=LG.signed_big(d, lg, in_mln))
    return C.L("delta_vs_current", d=LG.signed(d, lg), cur=cur_txt)


# --- KPI tiles -------------------------------------------------------------
# Row 1: who goes over limit. The headline is "over a positive limit" (the next order would be
# stopped although the customer has a limit); the total keeps the customers at limit 0 by rule
# visible next to it. Row 2: totals, each labelled with its population. Row 3: workload.
r1 = st.columns(4)
r1[0].metric(C.L("kpi_over_pos"), LG.num(k["over_new_positive_n"], lg),
             delta_cur(k["over_new_positive_n"] - k["over_current_positive_n"], LG.num(k["over_current_positive_n"], lg)),
             delta_color="inverse", border=True, help=C.L("help_over_pos", cur=LG.num(k["over_current_positive_n"], lg)))
with r1[1]:
    st.metric(C.L("kpi_over_n"), LG.num(k["over_new_n"], lg),
              delta_cur(k["over_new_n"] - k["over_current_n"], LG.num(k["over_current_n"], lg)),
              delta_color="off", border=True, help=C.L("help_over_n", cur=LG.num(k["over_current_n"], lg)))
    st.caption(C.L("kpi_over_split", z=LG.num(k["over_new_zero_n"], lg), p=LG.num(k["over_new_positive_n"], lg),
                   zc=LG.num(k["over_current_zero_n"], lg), pc=LG.num(k["over_current_positive_n"], lg)))
ex_m = abs(k["excess_new"]) >= 1e6
r1[2].metric(C.L("kpi_over_amt"), LG.big(k["excess_new"], lg),
             delta_cur(k["excess_new"] - k["excess_current"], LG.big(k["excess_current"], lg), ex_m, True),
             delta_color="inverse", border=True,
             help=C.L("help_over_amt", amt=LG.amt(k["excess_new"], lg), cur=LG.amt(k["excess_current"], lg)))
r1[3].metric(C.L("kpi_orders_over"), LG.num(k["orders_over_new_n"], lg),
             delta_cur(k["orders_over_new_n"] - k["orders_over_current_n"], LG.num(k["orders_over_current_n"], lg)),
             delta_color="inverse", border=True,
             help=C.L("help_orders_over", cur=LG.num(k["orders_over_current_n"], lg)))

r2 = st.columns(4)
lim_s = abs(k["limits_proposed_scope"]) >= 1e6
r2[0].metric(C.L("kpi_limits_scope", n=LG.num(k["n_scope"], lg)), LG.big(k["limits_proposed_scope"], lg),
             delta_cur(k["limits_proposed_scope"] - k["limits_current_scope"],
                       LG.big(k["limits_current_scope"], lg), lim_s, True),
             delta_color="off", border=True,
             help=C.L("help_limits_scope", amt=LG.amt(k["limits_proposed_scope"], lg),
                      cur=LG.amt(k["limits_current_scope"], lg)))
lim_m = abs(k["limits_proposed_active"]) >= 1e6
r2[1].metric(C.L("kpi_limits", n=LG.num(k["n_active"], lg)), LG.big(k["limits_proposed_active"], lg),
             delta_cur(k["limits_proposed_active"] - k["limits_current_active"],
                       LG.big(k["limits_current_active"], lg), lim_m, True),
             delta_color="off", border=True,
             help=C.L("help_limits", amt=LG.amt(k["limits_proposed_active"], lg),
                      cur=LG.amt(k["limits_current_active"], lg)))
r2[2].metric(C.L("kpi_exposure"), LG.big(k["exposure_active"], lg), border=True,
             help=C.L("help_exposure", amt=LG.amt(k["exposure_active"], lg)))
r2[3].metric(C.L("kpi_moves"), " / ".join(LG.num(k[x], lg) for x in ("higher_n", "lower_n", "equal_n")),
             border=True, help=C.L("help_moves"))

r3 = st.columns(4)
zc = k["zero_with_turnover_current_n"]
r3[0].metric(C.L("kpi_zero"), LG.num(k["zero_with_turnover_n_active"], lg),
             delta_cur(k["zero_with_turnover_n_active"] - zc, LG.num(zc, lg)), delta_color="off",
             border=True, help=C.L("help_zero", cur=LG.num(zc, lg)))
r3[1].metric(C.L("kpi_approval"), LG.num(k["approval_n"], lg), border=True,
             help=C.L("help_approval", pct=LG.pct(p.approval_threshold, lg), amt=LG.amt(p.approval_min_change, lg),
                      t1=LG.num(k["approval_tier1_n"], lg), t2=LG.num(k["approval_tier2_n"], lg),
                      t3=LG.num(k["approval_tier3_n"], lg)))
with r3[2]:
    if has_cerved:
        st.metric(C.L("kpi_review"), LG.num(k["plausibility_n"], lg), border=True,
                  help=C.L("help_review", pct=LG.pct(p.plausibility_threshold, lg)))
        st.caption(C.L("kpi_review_caption", amt=LG.big(k["plausibility_exposure"], lg)))
    else:
        st.metric(C.L("kpi_review"), "-", border=True, help=C.L("help_review_needs_cerved"))

st.caption(C.L("kpi_scope_caption", n=LG.num(k["n_scope"], lg), m=LG.num(k["n_active"], lg)) + " "
           + (C.L("kpi_cerved_mix", n=LG.num(k["in_cerved_n_active"], lg),
                  pct=LG.pct(k["in_cerved_exposure_share_active"], lg)) if has_cerved else ""))


# --- split by customer age (v3.2) -------------------------------------------
if p.age_bands_enabled:
    st.markdown(f"**{C.L('age_tbl_title')}**")
    ab = age_breakdown(res)
    rows_ab = [[LG.age_label(b, lg), LG.num(n, lg), LG.big(c, lg), LG.big(v, lg), LG.num(op, lg), LG.num(o, lg)]
               for b, n, c, v, op, o in zip(ab["age_band"], ab["n"], ab["limits_current"], ab["limits_proposed"],
                                             ab["over_new_positive_n"], ab["over_new_n"])]
    rows_ab.append([C.L("age_tbl_total"), LG.num(ab["n"].sum(), lg), LG.big(ab["limits_current"].sum(), lg),
                    LG.big(ab["limits_proposed"].sum(), lg), LG.num(ab["over_new_positive_n"].sum(), lg),
                    LG.num(ab["over_new_n"].sum(), lg)])
    st.markdown(C.md_table([C.L("age_col_band"), C.L("age_col_n"), C.L("age_col_cur"), C.L("age_col_new"),
                            C.L("age_col_over_pos"), C.L("age_col_over")], rows_ab, align="lrrrrr", bold_last=True))


# --- charts ----------------------------------------------------------------
def _style(chart: alt.Chart) -> alt.Chart:
    return (chart.configure_axis(labelFontSize=14, titleFontSize=15).configure_title(fontSize=16)
            .configure_legend(labelFontSize=14, titleFontSize=14, orient="bottom"))


cur_lab, new_lab = C.L("series_current"), C.L("series_new")
score_names = [LG.score_label(b, lg) for b in LG.BUCKET_ORDER]
col_a, col_b = st.columns(2)
with col_a:
    st.markdown(f"**{C.L('chart_over_by_score')}**")
    if not has_cerved:
        st.caption(C.L("chart_needs_cerved"))
    else:
        sb = score_breakdown(res)
        df = pd.concat([
            pd.DataFrame({"score": [LG.score_label(b, lg) for b in sb["score_bucket"]],
                          "series": cur_lab, "n": sb["over_current_n"].astype(int)}),
            pd.DataFrame({"score": [LG.score_label(b, lg) for b in sb["score_bucket"]],
                          "series": new_lab, "n": sb["over_new_n"].astype(int)})])
        df["label"] = df["n"].map(lambda v: LG.num(v, lg))
        base = alt.Chart(df).encode(
            y=alt.Y("score:N", sort=score_names, title=None, axis=alt.Axis(labelLimit=220)),
            yOffset=alt.YOffset("series:N", sort=[cur_lab, new_lab]),
            x=alt.X("n:Q", title=C.L("chart_over_by_score_x")))
        bars = base.mark_bar().encode(
            color=alt.Color("series:N", scale=alt.Scale(domain=[cur_lab, new_lab], range=[GREY, BLUE]),
                            title=None),
            tooltip=[alt.Tooltip("score:N", title=C.L("chart_score")),
                     alt.Tooltip("series:N", title=C.L("chart_series")),
                     alt.Tooltip("label:N", title=C.L("chart_over_by_score_x"))])
        text = base.mark_text(align="left", dx=4, fontSize=14).encode(text="label:N")
        st.altair_chart(_style((bars + text).properties(height=320)))

with col_b:
    st.markdown(f"**{C.L('chart_change_buckets')}**")
    scope = res[res["in_scope"]]
    b = pd.Series(LG.change_bucket(scope["current_limit"], scope["proposed_limit"]))
    counts = b.value_counts().reindex(LG.CHANGE_BUCKETS, fill_value=0)
    names = [C.L("b_" + x) for x in LG.CHANGE_BUCKETS]
    colors = [ORANGE, ORANGE, ORANGE, GREY, LIGHT_BLUE, LIGHT_BLUE, LIGHT_BLUE]
    df = pd.DataFrame({"bucket": names, "n": counts.values, "label": [LG.num(v, lg) for v in counts.values]})
    base = alt.Chart(df).encode(x=alt.X("bucket:N", sort=names, title=None,
                                              axis=alt.Axis(labelAngle=-35, labelOverlap=False, labelLimit=220)),
                                y=alt.Y("n:Q", title=C.L("chart_change_y")))
    bars = base.mark_bar().encode(
        color=alt.Color("bucket:N", scale=alt.Scale(domain=names, range=colors), legend=None),
        tooltip=[alt.Tooltip("bucket:N", title=C.L("chart_bucket")),
                 alt.Tooltip("label:N", title=C.L("chart_change_y"))])
    text = base.mark_text(dy=-8, fontSize=14).encode(text="label:N")
    st.altair_chart(_style((bars + text).properties(height=320)))

if has_cerved:
    with st.expander(C.L("chart_more")):
        st.markdown(f"**{C.L('chart_amounts_by_score')}**")
        sb = score_breakdown(res)
        series = [(C.L("series_current_limits"), "limits_current", GREY),
                  (C.L("series_new_limits"), "limits_proposed", BLUE),
                  (C.L("series_exposure"), "exposure", ORANGE)]
        df = pd.concat([pd.DataFrame({"score": [LG.score_label(x, lg) for x in sb["score_bucket"]],
                                      "series": lab, "v": sb[col] / 1e6}) for lab, col, _c in series])
        df["label"] = df["v"].map(lambda v: LG.num(v, lg, 2))
        snames = [s[0] for s in series]
        base = alt.Chart(df).encode(x=alt.X("score:N", sort=score_names, title=None, axis=alt.Axis(labelAngle=0, labelLimit=220)),
                                    xOffset=alt.XOffset("series:N", sort=snames),
                                    y=alt.Y("v:Q", title=C.L("mln")))
        bars = base.mark_bar().encode(
            color=alt.Color("series:N", scale=alt.Scale(domain=snames, range=[s[2] for s in series]), title=None),
            tooltip=[alt.Tooltip("score:N", title=C.L("chart_score")),
                     alt.Tooltip("series:N", title=C.L("chart_series")), alt.Tooltip("label:N", title=C.L("mln"))])
        text = base.mark_text(dy=-8, fontSize=13).encode(text="label:N")
        st.altair_chart(_style((bars + text).properties(height=320)))

# --- customer table ----------------------------------------------------------
st.subheader(C.L("tbl_title"))
f1, f2, f3 = st.columns([2.4, 2, 3.4])
search = f1.text_input(C.L("flt_search"), placeholder=C.L("flt_search_ph"), key="res_search")
scores = f2.multiselect(C.L("flt_score"), LG.BUCKET_ORDER, format_func=lambda x: LG.score_label(x, lg),
                        key="res_scores", placeholder=C.L("flt_all"))
ss.setdefault("res_change", "ALL")
change = f3.segmented_control(C.L("flt_change"), ["ALL", "HIGHER", "LOWER", "EQUAL"], key="res_change",
                              format_func=lambda x: tl({"ALL": "flt_all", "HIGHER": "flt_higher",
                                                         "LOWER": "flt_lower", "EQUAL": "flt_same"}[x]))
ages = st.multiselect(C.L("flt_age"), LG.AGE_ORDER, format_func=lambda x: LG.age_label(x, lg), key="res_ages",
                      placeholder=C.L("flt_all")) if p.age_bands_enabled else []
only = st.pills(C.L("flt_only"), ["over_new", "becomes_over", "leaves_over", "review", "approval"],
                selection_mode="multi", key="res_only", format_func=lambda x: tl("flt_" + x))

t1, t1b, t2 = st.columns([1.3, 1.3, 1.2], vertical_alignment="center")
scope_all = t1.toggle(C.L("flt_scope_all"), key="res_scope_all", help=C.L("flt_scope_all_help"))
more_cols = t1b.toggle(C.L("flt_more_cols"), key="res_more_cols", help=C.L("flt_more_cols_help"))
ref = LG.date_str(C.ref_date(data)).replace("/", "-")
t2.download_button(C.L("btn_excel"), data=C.excel_bytes(key, res), file_name=C.L("excel_filename", date=ref),
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   icon=":material/download:", help=C.L("btn_excel_help"), key="res_excel")

tbl = C.customer_table(key, res)
mask = pd.Series(True, index=res.index) if scope_all else res["in_scope"].copy()
if search:
    q = search.strip().lower()
    mask &= res["code"].str.lower().str.contains(q, regex=False) | \
        res["name"].fillna("").str.lower().str.contains(q, regex=False)
if scores:
    mask &= res["score_bucket"].isin(scores)
if ages:
    mask &= res["age_band"].isin(ages)
if change and change != "ALL":
    mask &= res["direction"].eq(change)
for o in only or []:
    mask &= {"over_new": res["over_new"], "becomes_over": res["over_new"] & ~res["over_current"],
             "leaves_over": ~res["over_new"] & res["over_current"], "review": res["plausibility_flag"],
             "approval": res["approval_needed"]}[o]
total = int(res["in_scope"].sum()) if not scope_all else len(res)
view = tbl[mask.values].sort_values("exposure", ascending=False).reset_index(drop=True)
st.caption(C.L("tbl_count", shown=LG.num(len(view), lg), total=LG.num(total, lg)) + " · " + C.L("tbl_select_hint"))

if view.empty:
    st.info(C.L("tbl_empty"), icon=":material/filter_alt_off:")
else:
    slot = st.empty()
    cc = st.column_config
    # main columns fit 1366 px without horizontal scrolling; the others on request
    config = {
        "code": cc.TextColumn(C.L("col_code"), width=76),
        "name": cc.TextColumn(C.L("col_name"), width=160),
        "cur": cc.NumberColumn(C.L("col_cur"), width=95),
        "new": cc.NumberColumn(C.L("col_new"), width=100),
        "diff": cc.NumberColumn(C.L("col_diff"), width=105),
        "over": cc.TextColumn(C.L("col_over"), width=72, help=C.L("col_over_help")),
        "reason": cc.TextColumn(C.L("col_reason"), width=218),
        "score": cc.TextColumn(C.L("col_score"), width="small"),
        "age": cc.TextColumn(C.L("col_age"), width="small"),
        "exposure": cc.NumberColumn(C.L("col_exposure")),
        "overdue": cc.NumberColumn(C.L("col_overdue")),
        "why": cc.TextColumn(C.L("col_why"), width="large"),
        "flags": cc.TextColumn(C.L("col_flags"), width="small"),
    }
    cols = LG.TABLE_MAIN + ([c for c in LG.TABLE_MORE if c != "age" or p.age_bands_enabled] if more_cols else [])
    sty = C.styler(view[cols], [c for c in ("exposure", "overdue", "cur", "new") if c in cols],
                   signed=["diff"], bold=["new"])
    ev = st.dataframe(sty, hide_index=True, width="stretch", height=520, on_select="rerun",
                      selection_mode="single-row", column_config={c: config[c] for c in cols},
                      key="res_table")
    sel = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
    if sel:
        row = view.iloc[sel[0]]
        if slot.button(C.L("btn_open_customer", name=row["name"]), type="primary", icon=":material/person_search:"):
            ss.customer = row["code"]
            st.switch_page(C.PAGE_FILES["customer"])
