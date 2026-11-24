"""Page "Regole / Rules": which rules are active? (UX.md section 7)"""
from __future__ import annotations

import streamlit as st

from core import texts as TX
from ui import common as C
from ui import logic as LG

lg = C.lang()
data, key = C.get_data()
p = C.params()

C.page_header("rules", data)

n_scope = C.simulate(data, key)["kpi"]["n_scope"] if data.ok else None
sections = LG.rules(p, n_scope, lg, C.ref_date(data) if data.ok else None)
md = LG.rules_markdown(sections, lg)

left, right = st.columns([3, 2], gap="large")
with left:
    for head, text in md.items():
        st.subheader(C.L(head))
        st.markdown(text)
    st.download_button(C.L("rules_download"), data=LG.rules_text(sections, lg).encode("utf-8"),
                       file_name=C.L("rules_filename"), mime="text/plain", icon=":material/download:",
                       key="rules_txt")

with right:
    st.subheader(C.L("gloss_title"))
    st.markdown("\n".join(f"- **{C.L(g + '_t')}**: {C.L(g)}" for g in LG.GLOSSARY))
    st.subheader(C.L("classes_title"))
    rows = []
    for cls in list(p.exempt_classes) + list(p.special_classes):
        rule = C.L("classes_rule_exempt" if cls in p.exempt_classes else "classes_rule_special")
        rows.append([cls, TX.CLASS_TEXTS.get(cls, {}).get(lg, "-"), rule])
    st.markdown(C.md_table([C.L("classes_col_class"), C.L("classes_col_meaning"), C.L("classes_col_rule")], rows))
