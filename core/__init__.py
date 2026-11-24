"""Calculation core of the SIAD credit-limit simulator (v4, multi-country).

No Streamlit and no network here: the UI (app.py) only calls these modules.
"""
from .loaders import LoadedData, Finding, LoaderError, load_files, load_folder
from .params import Params, PARAM_META
from .engine import simulate, payment_days

__all__ = [
    "LoadedData", "Finding", "LoaderError", "load_files", "load_folder",
    "Params", "PARAM_META", "simulate", "payment_days",
]
