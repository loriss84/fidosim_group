"""Page "Dati / Data": are the three files there and can we trust them? (UX.md section 2)"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.kpi import data_summary
from ui import common as C
from ui import logic as LG

ss = st.session_state
lg = C.lang()
data, key = C.get_data()
p = C.params()

C.page_header("data", data, banner=False)


def _on_upload() -> None:
    files = ss.get("upload_files") or []
    ss.uploads = [(f.name, f.getvalue()) for f in files]


def _clear_uploads() -> None:
    ss.uploads = []


# --- 1. three file cards --------------------------------------------------
uploaded = C.uploaded_kinds(data)
cols = st.columns(4)
for col, kind in zip(cols, ("checkfidi", "cerved", "ar124", "md105")):
    with col, st.container(border=True):
        st.markdown(f"**{C.L('file_' + kind)}**")
        if kind in data.sources:
            st.markdown(f":green-badge[:material/check: {C.L('file_loaded')}]")
            extra = f" · {C.L('file_uploaded')}" if kind in uploaded else ""
            st.caption(f"{data.sources[kind]} · {C.L('file_rows', n=LG.num(data.rows_read[kind], lg))}{extra}")
            st.write(C.L(f"file_{kind}_role"))
        else:
            if kind == "md105":   # optional file: grey, not a warning
                st.markdown(f":gray-badge[{C.L('file_missing')}]")
            else:
                st.markdown(f":orange-badge[:material/warning: {C.L('file_missing')}]")
            st.write(C.L(f"file_{kind}_role"))
            impact = {"checkfidi": C.L("missing_checkfidi_impact"),
                      "cerved": C.L("missing_cerved_impact", coef=LG.coef(p.coef_not_in_cerved, lg)),
                      "ar124": C.L("missing_ar124_impact", days=LG.num(p.fallback_days, lg)),
                      "md105": C.L("file_md105_missing")}[kind]
            st.caption(impact)

for f in data.findings:
    if f.code in ("FILE_INVALID", "FILE_DUPLICATE_KIND"):
        (st.error if f.code == "FILE_INVALID" else st.warning)(LG.file_error(f, lg))

# --- 2. upload area -------------------------------------------------------
with st.expander(C.L("upload_title"), expanded=bool(data.missing), icon=":material/upload_file:"):
    st.file_uploader(C.L("upload_label"), type=["xlsx", "xls"], accept_multiple_files=True,
                     key="upload_files", on_change=_on_upload)
    st.caption(C.L("upload_help"))
    if ss.uploads:
        st.caption(C.L("upload_active", names=", ".join(n for n, _b in ss.uploads)))
        st.button(C.L("btn_clear_uploads"), on_click=_clear_uploads, icon=":material/folder:")

if not data.ok:
    st.info(C.L("empty_data"), icon=":material/info:")
    st.stop()

# --- 3. population --------------------------------------------------------
sim = C.simulate(data, key)
res, k = sim["res"], sim["kpi"]
s = data_summary(data, p)
st.subheader(C.L("data_population"))
m = st.columns(5)
m[0].metric(C.L("m_rows_checkfidi"), LG.num(data.rows_read.get("checkfidi"), lg), help=C.L("help_rows_checkfidi"))
m[1].metric(C.L("m_active"), LG.num(s["n_active"], lg), help=C.L("help_active"))
m[2].metric(C.L("m_intercompany"), LG.num(s["n_intercompany_excluded"], lg), help=C.L("help_intercompany"))
m[3].metric(C.L("m_scope"), LG.num(k["n_scope"], lg), help=C.L("help_scope"))
m[4].metric(C.L("m_ref_date"), LG.date_str(s["reference_date"]), help=C.L("help_ref_date"))

# --- 4. Cerved matching ---------------------------------------------------
if data.cerved is not None:
    st.subheader(C.L("data_matching"))
    orphans = next((f.count for f in data.findings_for(p.cerved_reject_vat_conflict) if f.code == "CV_UNMATCHED"), 0)
    m = st.columns(4)
    m[0].metric(C.L("m_match_code"), LG.num(s["match_code_n"], lg), help=C.L("help_match_code"))
    m[1].metric(C.L("m_match_vat"), LG.num(s["match_vat_n"], lg), help=C.L("help_match_vat"))
    m[2].metric(C.L("m_match_none"), LG.num(s["match_none_n"], lg), help=C.L("help_match_none"))
    m[3].metric(C.L("m_cerved_orphans"), LG.num(orphans, lg), help=C.L("help_cerved_orphans"))
    st.caption(C.L("data_cerved_share", n=LG.num(k["in_cerved_n_active"], lg),
                   pct=LG.pct(k["in_cerved_exposure_share_active"], lg)))

# --- 5. quality table -----------------------------------------------------
st.subheader(C.L("data_quality"))
checks = LG.quality_checks(data, res, p, lg)
if not checks:
    st.success(C.L("dq_all_ok"), icon=":material/check_circle:")
else:
    tbl = pd.DataFrame({C.L("dq_col_check"): [c["check"] for c in checks],
                        C.L("dq_col_count"): [c["count"] for c in checks],
                        C.L("dq_col_meaning"): [c["meaning"] for c in checks]})
    # static table: the meaning sentences wrap instead of being cut (UX 8)
    st.markdown(C.md_table([C.L("dq_col_check"), C.L("dq_col_count"), C.L("dq_col_meaning")],
                           [[c["check"], LG.num(c["count"], lg), c["meaning"]] for c in checks], align="lrl"))
    with st.expander(C.L("dq_details")):
        idx = st.selectbox(C.L("dq_pick"), range(len(checks)), format_func=lambda i: checks[i]["check"],
                           key="dq_pick")
        chk = checks[idx]
        if chk["rows"] is not None and len(chk["rows"]):
            st.dataframe(chk["rows"], hide_index=True, width="stretch", height=300)
        elif chk["examples"]:
            st.caption(C.L("dq_examples", list=", ".join(map(str, chk["examples"][:20]))))

# --- 6. data settings -----------------------------------------------------
default_ref = data.default_reference_date


def _on_settings() -> None:
    d = ss.get("w_ref_date")
    iso = pd.Timestamp(d).date().isoformat() if d else None
    if default_ref is not None and iso == default_ref.date().isoformat():
        iso = None  # same as the automatic date: keep "automatic"
    C.set_params(C.params().replace(reference_date=iso, window_months=int(ss.get("w_window", 12))))


with st.expander(C.L("data_settings"), icon=":material/event:"):
    st.caption(C.L("data_settings_help"))
    ss.setdefault("w_ref_date", C.ref_date(data).date())
    ss.setdefault("w_window", int(p.window_months))
    c1, c2 = st.columns(2)
    c1.date_input(C.L("p_ref_date"), key="w_ref_date", format="DD/MM/YYYY", help=C.L("p_ref_date_help"),
                  on_change=_on_settings)
    c2.number_input(C.L("p_window_months"), min_value=1, max_value=36, step=1, key="w_window",
                    help=C.L("p_window_months_help"), on_change=_on_settings)
