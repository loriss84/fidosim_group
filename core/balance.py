"""Public balance sheet of a Romanian customer (ANAF web service) and a second opinion on the limit.

The second opinion (``assess``) is the same for every country; the other countries' sources are in
``core.bs_providers`` and give their figures with the keys of ``FIELDS``.

NOT part of the limit formula: the Customer page shows it on request, next to the proposed limit.

Source: ANAF public web service, no authentication, one CUI and one year per call:
    GET https://webservicesp.anaf.ro/bilant?an=<year>&cui=<cui>
Answer: {"an", "cui", "deni", "caen", "den_caen", "i": [{"indicator", "val_indicator", "val_den_indicator"}]}.
A year not filed (or a CUI that does not exist) answers with an empty "i". ANAF allows at most one
request per second. Indicator codes differ by type of statement, so values are read by description.
Public bodies (hospitals, town halls) file other reports and are not in this service.

No Streamlit here: the page calls ``lookup`` and ``assess``.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

URL = "https://webservicesp.anaf.ro/bilant?an={year}&cui={cui}"
MIN_INTERVAL_S = 1.1          # ANAF: max 1 request per second
_last_call = [0.0]

# key -> description prefixes (lower case, no diacritics); first match wins
FIELDS: dict[str, tuple[str, ...]] = {
    "fixed_assets": ("active imobilizate",),
    "current_assets": ("active circulante",),
    "inventory": ("stocuri",),
    "receivables": ("creante",),
    "cash": ("casa si conturi",),
    "debts": ("datorii",),
    "provisions": ("provizioane",),
    "equity": ("capitaluri - total", "capitaluri proprii", "capitaluri total", "total capitaluri", "capitaluri"),
    "share_capital": ("capital subscris",),
    "turnover": ("cifra de afaceri",),
    "total_revenue": ("venituri totale",),
    "total_expenses": ("cheltuieli totale",),
    "gross_profit": ("profit brut",),
    "gross_loss": ("pierdere bruta",),
    "net_profit": ("profit net",),
    "net_loss": ("pierdere neta",),
    "employees": ("numar mediu",),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_indicators(items: list[dict[str, Any]]) -> dict[str, float]:
    """ANAF indicator list -> {field key: value}, matched on the description."""
    out: dict[str, float] = {}
    for it in items or []:
        d = _norm(it.get("val_den_indicator", ""))
        v = it.get("val_indicator")
        if v is None:
            continue
        for key, prefixes in FIELDS.items():
            if key not in out and any(d.startswith(p) for p in prefixes):
                out[key] = float(v)
                break
    return out


def cui_from_vat(*vats: Any) -> tuple[str | None, str]:
    """First usable Romanian CUI among the VAT values: ('13165477', 'ok') / (None, 'foreign' | 'missing')."""
    foreign = False
    for v in vats:
        if v is None or (isinstance(v, float) and v != v):
            continue
        s = re.sub(r"[^A-Z0-9]", "", str(v).upper())
        if not s:
            continue
        if s.startswith("RO"):
            s = s[2:]
        if re.fullmatch(r"\d{2,10}", s):
            return str(int(s)), "ok"
        foreign = True
    return None, "foreign" if foreign else "missing"


def _http_get(url: str, timeout: float) -> dict[str, Any]:
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SIAD-FidoSim/3.2"})
        with urllib.request.urlopen(req, timeout=timeout) as r:   # system proxy settings are used
            return json.loads(r.read().decode("utf-8"))
    finally:
        _last_call[0] = time.monotonic()


def lookup(cui: str, today: date | None = None, years_back: int = 3, cache_dir: Path | None = None,
           refresh: bool = False, timeout: float = 20.0,
           fetch: Callable[[str, float], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Latest filed balance sheet of ``cui``: tries last year, then the years before.

    Returns ``{"status": "ok" | "not_found" | "error", "cui", "year", "name", "caen", "caen_desc",
    "values", "raw", "url", "years_tried", "fetched_at", "error"}``. Answers are cached per CUI in
    ``cache_dir`` (``refresh`` ignores the cache).
    """
    fetch = fetch or _http_get
    today = today or date.today()
    cache = Path(cache_dir) / f"anaf_{cui}.json" if cache_dir else None
    if cache and cache.exists() and not refresh:
        try:
            res = json.loads(cache.read_text(encoding="utf-8"))
            if res.get("status") in ("ok", "not_found"):
                res["from_cache"] = True
                return res
        except (OSError, ValueError):
            pass
    tried: list[int] = []
    res: dict[str, Any] = {"cui": cui, "status": "not_found", "years_tried": tried,
                           "fetched_at": datetime.now().isoformat(timespec="seconds")}
    for year in range(today.year - 1, today.year - 1 - years_back, -1):
        url = URL.format(year=year, cui=cui)
        tried.append(year)
        try:
            j = fetch(url, timeout)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            res.update(status="error", error=str(getattr(e, "reason", e)), url=url)
            return res
        items = j.get("i") or []
        if items:
            res.update(status="ok", year=year, url=url, name=(j.get("deni") or "").strip(),
                       caen=j.get("caen"), caen_desc=(j.get("den_caen") or "").strip(),
                       values=parse_indicators(items),
                       raw=[(i.get("indicator"), (i.get("val_den_indicator") or "").strip(), i.get("val_indicator"))
                            for i in items])
            break
    res["url"] = res.get("url") or URL.format(year=tried[0], cui=cui)
    if cache:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    res["from_cache"] = False
    return res


# ---------------------------------------------------------------------------
# Second opinion on the proposed limit
# ---------------------------------------------------------------------------
@dataclass
class BalanceParams:
    equity_share: float = 0.10         # a healthy company can carry a limit up to 10% of its net equity
    weak_equity_share: float = 0.05    # ... 5% if it has a weakness (loss, heavy debts, low liquidity)
    max_debt_to_equity: float = 3.0    # more debt than 3x equity: weakness
    min_liquidity: float = 0.8         # current assets / total debts below 0.8: weakness
    max_age_months: int = 18           # balance-sheet year end older than this: the reading is not current
    round_to: int = 1000               # suggested limit rounded down to this


VERDICTS = ("valid", "valid_watch", "too_high", "zero_confirmed", "zero_formula", "na")


@dataclass
class Assessment:
    verdict: str                       # one of VERDICTS
    capacity: float | None             # limit the balance sheet can carry (equity x share, rounded down)
    suggested: float | None            # the correct limit according to the balance sheet
    share_used: float | None           # equity share used for the capacity (10% or 5%)
    weaknesses: list[str] = field(default_factory=list)   # 'loss', 'leverage', 'liquidity'
    old: bool = False                  # balance sheet older than max_age_months
    age_months: int = 0
    ratios: dict[str, float | None] = field(default_factory=dict)


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def assess(values: dict[str, float], year: int, proposed: float, current: float,
           siad_turnover_12m: float | None = None, today: date | None = None,
           bp: BalanceParams | None = None, period_end_month: int = 12) -> Assessment:
    """Is the proposed limit right for this company, and if not, what is?

    Capacity = net equity x ``equity_share`` (10%), or x ``weak_equity_share`` (5%) when the company
    has a weakness: a net loss, debts above ``max_debt_to_equity`` x equity, current assets below
    ``min_liquidity`` x debts. Rounded down to ``round_to``. Net equity <= 0 -> capacity 0.

    - proposed <= capacity: 'valid' (no weakness) or 'valid_watch' (weakness or old balance sheet);
      the suggested limit is the proposed one.
    - proposed > capacity: 'too_high'; the suggested limit is the capacity.
    - proposed 0: 'zero_confirmed' when the capacity is 0, else 'zero_formula' (the 0 comes from the
      formula; the balance sheet alone would allow the capacity).
    - no net equity in the published statement: 'na'.
    """
    bp = bp or BalanceParams()
    today = today or date.today()
    eq = values.get("equity")
    to = values.get("turnover")
    debts = values.get("debts")
    net = None
    if "net_profit" in values or "net_loss" in values:
        net = values.get("net_profit", 0.0) - values.get("net_loss", 0.0)
    pos_eq = eq if eq is not None and eq > 0 else None
    ratios = {
        "net_result": net,
        "net_margin": _div(net, to),
        "debt_to_equity": _div(debts, pos_eq),
        "liquidity": _div(values.get("current_assets"), debts),
        "limit_on_equity": _div(proposed, pos_eq),
        "current_on_equity": _div(current, pos_eq),
        "siad_share": _div(siad_turnover_12m, to),
    }
    age = max(0, (today.year - year) * 12 + today.month - int(period_end_month or 12))
    old = age > bp.max_age_months
    if eq is None:
        return Assessment("na", None, None, None, [], old, age, ratios)
    weak: list[str] = []
    if net is not None and net < 0:
        weak.append("loss")
    if ratios["debt_to_equity"] is not None and ratios["debt_to_equity"] > bp.max_debt_to_equity:
        weak.append("leverage")
    if ratios["liquidity"] is not None and ratios["liquidity"] < bp.min_liquidity:
        weak.append("liquidity")
    if eq <= 0:
        share, capacity = None, 0.0
    else:
        share = bp.weak_equity_share if weak else bp.equity_share
        capacity = float(int(eq * share // bp.round_to) * bp.round_to)
    if proposed <= 0:
        v = "zero_confirmed" if capacity <= 0 else "zero_formula"
        return Assessment(v, capacity, 0.0, share, weak, old, age, ratios)
    if proposed > capacity:
        return Assessment("too_high", capacity, capacity, share, weak, old, age, ratios)
    v = "valid_watch" if (weak or old) else "valid"
    return Assessment(v, capacity, float(proposed), share, weak, old, age, ratios)
