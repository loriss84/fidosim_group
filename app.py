"""Simulatore Fido SIAD Romania (v3): Streamlit entry point.

Thin shell: page config, navigation and sidebar. The pages are in ui/pages/, the shared
state in ui/common.py, the calculation in core/. Start with run.bat (Windows) or run.sh.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from ui import common as C  # noqa: E402

C.init_state()
st.set_page_config(page_title=C.L("app_title"), layout="wide", initial_sidebar_state="expanded")
st.markdown(C.CSS, unsafe_allow_html=True)

data, _key = C.get_data()
default = "results" if data.ok else "data"
spec = [("data", "nav_data", ":material/folder_open:"),
        ("results", "nav_results", ":material/insights:"),
        ("customer", "nav_customer", ":material/person_search:"),
        ("lab", "nav_lab", ":material/tune:"),
        ("rules", "nav_rules", ":material/menu_book:")]
pages = [st.Page(C.PAGE_FILES[k], title=C.L(t), icon=icon, url_path=k, default=(k == default))
         for k, t, icon in spec]
nav = st.navigation(pages, position="sidebar")
C.sidebar(data)
nav.run()
