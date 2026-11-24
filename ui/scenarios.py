"""Saved scenarios: one JSON file per scenario in the workspace folder. No Streamlit here.

File format: {"name": str, "saved_at": ISO timestamp, "params": {Params.to_dict()}}.
Import also accepts a bare parameters dict. Unknown parameter keys are ignored and reported.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

from core.params import Params

KNOWN = {f.name for f in fields(Params)}


def slug(name: str) -> str:
    """'Moltiplicatore 2,5' -> 'moltiplicatore-2-5' (safe file name)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:60] or "scenario"


def _path(folder: Path, name: str) -> Path:
    return Path(folder) / f"{slug(name)}.json"


def exists(folder: Path, name: str) -> bool:
    return _path(folder, name).exists()


def save(folder: Path, name: str, params: Params) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = _path(folder, name)
    doc = {"name": name.strip(), "saved_at": datetime.now().isoformat(timespec="seconds"),
           "params": params.to_dict()}
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def parse(raw: bytes | str, fallback_name: str = "scenario") -> tuple[str, Params, list[str]]:
    """(name, params, ignored keys) from JSON text. Raises ValueError if not a valid scenario."""
    try:
        doc = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception as e:
        raise ValueError("not JSON") from e
    if not isinstance(doc, dict):
        raise ValueError("not an object")
    d = doc.get("params", doc)
    if not isinstance(d, dict) or not (set(d) & KNOWN):
        raise ValueError("no parameters")
    try:
        params = Params.from_dict(d)
    except Exception as e:
        raise ValueError(str(e)) from e
    if params.validate():
        raise ValueError("; ".join(params.validate()))
    name = str(doc.get("name") or fallback_name).strip() or fallback_name
    ignored = sorted(k for k in d if k not in KNOWN)
    return name, params, ignored


def list_all(folder: Path) -> list[dict[str, Any]]:
    """Valid scenarios in the folder, sorted by name: {name, file, saved_at, params}."""
    out = []
    folder = Path(folder)
    if not folder.exists():
        return out
    for f in sorted(folder.glob("*.json")):
        try:
            raw = f.read_text(encoding="utf-8")
            name, params, _ = parse(raw, f.stem)
            saved = json.loads(raw).get("saved_at", "")
        except Exception:
            continue
        out.append({"name": name, "file": f.name, "saved_at": saved, "params": params})
    return sorted(out, key=lambda s: s["name"].lower())


def delete(folder: Path, file_name: str) -> None:
    p = Path(folder) / Path(file_name).name
    if p.exists():
        p.unlink()


def export_bytes(folder: Path, file_name: str) -> bytes:
    return (Path(folder) / Path(file_name).name).read_bytes()
