"""Snapshot of everything the simulator computes and writes for the synthetic Romanian data.

``python -m tests.golden write`` stores the snapshot in ``tests/fixtures/golden_ro.json.gz``; it was
written ONCE with the single-country simulator (fidosim_romania, commit 30d71e7) before the
multi-country changes. ``tests/test_golden.py`` recomputes it with the current code and compares:
the Romanian results, texts and Excel must not change by one unit.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FIXTURE = Path(__file__).parent / "fixtures" / "golden_ro.json.gz"


def _scenarios():
    from core import params as P
    base = P.Params()
    return {
        "default": base,
        "v31": P.Params(**P.V31),
        "old_v3": P.Params(**P.OLD_V3),
        "legacy": P.Params(ceiling_is_hard=False, cerved_reject_vat_conflict=False, terms_positive_only=False),
        "variant": base.replace(multiplier=2.5, rounding_mode="down", rounding_step=500, min_limit=3000,
                                coef_not_in_cerved=0.6, buffer=0.15, approval_threshold=0.3),
        "measured": base.replace(m1_days_basis="measured", cerved_cap_enabled=False),
    }


def _df(df: pd.DataFrame) -> dict[str, Any]:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d").where(df[c].notna(), None)
    return json.loads(df.to_json(orient="split", double_precision=12, default_handler=str))


def snapshot() -> dict[str, Any]:
    warnings.filterwarnings("ignore")
    from core import engine, explain
    from core.export import to_excel
    from core.kpi import kpis
    from core.loaders import load_files
    from tests import synthetic as S
    from ui import logic as LG

    files = S.files("RO")
    datasets = {"full": load_files(files),
                "no_md105": load_files([f for f in files if not f[0].startswith("md105")]),
                "no_cerved": load_files([f for f in files if not f[0].startswith("cerved")])}
    out: dict[str, Any] = {}
    for dname, data in datasets.items():
        for sname, p in _scenarios().items():
            if dname != "full" and sname not in ("default", "v31"):
                continue
            key = f"{dname}/{sname}"
            r = engine.simulate(data, p, include_all=True)
            res = r[r["is_active"] & ~r["is_intercompany"]].reset_index(drop=True)
            entry: dict[str, Any] = {"result": _df(r), "kpi": {k: (None if isinstance(v, float) and math.isnan(v)
                                                                   else v) for k, v in kpis(res).items()}}
            for lang in ("it", "en"):
                entry[f"texts_{lang}"] = _df(explain.add_texts(res, p, lang)[["code", "reason", "why_change"]])
                entry[f"table_{lang}"] = _df(LG.customer_table(res, p, lang))
                entry[f"steps_{lang}"] = {c: LG.step_rows(res[res["code"] == c].iloc[0], p, lang)
                                          for c in res["code"].iloc[::7]}
                entry[f"rules_{lang}"] = LG.rules_text(LG.rules(p, int(res["in_scope"].sum()), lang), lang)
                entry[f"quality_{lang}"] = [{k: v for k, v in q.items() if k in ("key", "check", "count", "meaning")}
                                            for q in LG.quality_checks(data, res, p, lang)]
                if sname == "default":
                    xl = pd.read_excel(io.BytesIO(to_excel(res, p, lang)), sheet_name=None)
                    entry[f"excel_{lang}"] = {s: _df(d) for s, d in xl.items()}
            out[key] = entry
    return json.loads(json.dumps(out, default=str))


def write() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as f:
        json.dump(snapshot(), f, ensure_ascii=False)
    print(f"written {FIXTURE} ({FIXTURE.stat().st_size // 1024} KB)")


def load() -> dict[str, Any]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        return json.load(f)


def compare(a: Any, b: Any, path: str = "", out: list[str] | None = None, limit: int = 30) -> list[str]:
    """Differences between two snapshots (floats equal within 1e-9 relative)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'new' if k in b else 'golden'}")
            else:
                compare(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{path}[{i}]", out, limit)
    elif isinstance(a, float) and isinstance(b, (int, float)) or isinstance(b, float) and isinstance(a, (int, float)):
        if not (abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))):
            out.append(f"{path}: {a!r} != {b!r}")
    elif a != b:
        out.append(f"{path}: {str(a)[:160]!r} != {str(b)[:160]!r}")
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        write()
    else:
        d = compare(load(), snapshot())
        print("identical" if not d else "\n".join(d))
