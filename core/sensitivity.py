"""One-parameter sensitivity analysis (reuses cached payment days on the data object)."""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from .engine import simulate
from .kpi import kpis
from .loaders import LoadedData
from .params import Params, PARAM_META

DEFAULT_KPIS = ["limits_proposed_active", "over_new_n", "excess_new", "higher_n", "lower_n",
                "equal_n", "zero_with_turnover_n_active", "orders_over_new_n", "approval_n"]


def sensitivity(data: LoadedData, params: Params, key: str, values: Iterable[Any],
                kpi_keys: list[str] | None = None) -> pd.DataFrame:
    """Simulate once per value of parameter ``key`` (others from ``params``).

    Returns a DataFrame with column ``value`` plus the requested KPI keys (default
    DEFAULT_KPIS; pass ``kpi_keys=[]`` for all). Invalid values raise ValueError.
    """
    if key not in PARAM_META:
        raise KeyError(f"unknown parameter {key!r}")
    keys = DEFAULT_KPIS if kpi_keys is None else kpi_keys
    rows = []
    for v in values:
        k = kpis(simulate(data, params.replace(**{key: v})))
        row = {"value": v}
        row.update({kk: k[kk] for kk in (keys or k.keys())})
        rows.append(row)
    return pd.DataFrame(rows)


def value_range(key: str, start: float, stop: float, n: int = 10) -> list[float]:
    """``n`` evenly spaced values between start and stop, snapped to the parameter step."""
    meta = PARAM_META[key]
    if n < 2:
        return [start]
    vals = [start + (stop - start) * i / (n - 1) for i in range(n)]
    step = meta.get("step")
    if step:
        vals = [round(round(v / step) * step, 10) for v in vals]
    if meta["kind"] == "int":
        vals = [int(round(v)) for v in vals]
    return list(dict.fromkeys(vals))
