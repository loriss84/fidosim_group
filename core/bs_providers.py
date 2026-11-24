"""Public balance sheets by country: one interface, one source per country.

Every provider answers the same questions for the Customer page:

- ``key_from(*vats)``: the local tax id to look up, from the VAT numbers of Check fidi / Cerved
  -> ``(key, "ok")`` or ``(None, "foreign" | "missing")``;
- ``lookup(key, cache_dir, refresh)``: the latest balance sheet as a dict
  ``{"status": "ok" | "not_found" | "no_data" | "error", "key", "cui" (= key, as the Romanian page
  used it), "year", "period_end_month", "name", "caen_desc" (activity), "values", "raw", "url",
  "years_tried", "fetched_at", "error", "source", "note"}``.
  ``values`` uses the keys of ``balance.FIELDS`` (equity, debts, current_assets, turnover...), so
  ``balance.assess`` gives the same second opinion everywhere;
- ``search_url(key)``: the register's page for the customer, to check by hand.

Sources:
- Romania: ANAF web service (``core.balance``), automatic;
- Slovakia: RÚZ open API (Register účtovných závierok, Ministry of Finance), automatic, no key;
- Austria, Czech Republic, Germany, Hungary: no free machine-readable source usable without a key
  (Austria: Firmenbuch HVD with an API key, not connected yet). The page opens the register and the
  user types the few figures needed; they are saved on this PC (``ManualProvider``).

No Streamlit here. Network calls only in ``lookup`` (never during a simulation).
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from . import balance as ANAF
from .country import Country, get

Fetch = Callable[[str, float], Any]


def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _alnum(v: Any) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(v).upper())


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_cache(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        res = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return res if res.get("status") in ("ok", "not_found", "no_data") else None


def _write_cache(path: Path | None, res: dict[str, Any]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


class Provider:
    """Base class. ``automatic`` = the page can read the balance sheet with one click."""
    source = ""
    automatic = False

    def __init__(self, country: Country) -> None:
        self.country = country

    # -- identification ---------------------------------------------------------------------------
    def key_from(self, *vats: Any) -> tuple[str | None, str]:
        foreign = False
        p = self.country.vat_prefix
        for v in vats:
            s = _alnum(v)
            if not s:
                continue
            if s[:2].isalpha() and s[:2] != p:
                foreign = True
                continue
            if s.startswith(p):
                s = s[len(p):]
            k = self._key(s)
            if k:
                return k, "ok"
        return None, "foreign" if foreign else "missing"

    def _key(self, s: str) -> str | None:
        return s if len(s) >= 4 else None

    def cache_path(self, key: str, cache_dir: Path | None) -> Path | None:
        return Path(cache_dir) / f"{self.source}_{self.country.code}_{key}.json" if cache_dir else None

    def search_url(self, key: str | None) -> str:
        return self.country.register_url.replace("{key}", urllib.parse.quote(key or ""))

    def cached(self, key: str, cache_dir: Path | None) -> dict[str, Any] | None:
        """What is already saved on this PC (no network)."""
        res = _read_cache(self.cache_path(key, cache_dir))
        if res is not None:
            res["from_cache"] = True
        return res

    def lookup(self, key: str, cache_dir: Path | None = None, refresh: bool = False,
               today: date | None = None, fetch: Fetch | None = None) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Romania: ANAF (the single-country simulator's code, unchanged)
# ---------------------------------------------------------------------------
class AnafProvider(Provider):
    source = "anaf"
    automatic = True

    def key_from(self, *vats: Any) -> tuple[str | None, str]:
        return ANAF.cui_from_vat(*vats)

    def cache_path(self, key: str, cache_dir: Path | None) -> Path | None:
        return Path(cache_dir) / f"anaf_{key}.json" if cache_dir else None

    def search_url(self, key: str | None) -> str:
        return ANAF.URL.format(year=date.today().year - 1, cui=key or "")

    def cached(self, key: str, cache_dir: Path | None) -> dict[str, Any] | None:
        p = self.cache_path(key, cache_dir)
        return ANAF.lookup(key, cache_dir=cache_dir) if p is not None and p.exists() else None

    def lookup(self, key: str, cache_dir: Path | None = None, refresh: bool = False,
               today: date | None = None, fetch: Fetch | None = None) -> dict[str, Any]:
        res = ANAF.lookup(key, today=today, cache_dir=cache_dir, refresh=refresh, fetch=fetch)
        res.setdefault("key", key)
        res.setdefault("source", "anaf")
        return res


# ---------------------------------------------------------------------------
# Slovakia: RÚZ open API
# ---------------------------------------------------------------------------
RUZ_API = "https://www.registeruz.sk/cruz-public/api"
RUZ_WEB = "https://www.registeruz.sk/cruz-public/domain"
RUZ_MIN_INTERVAL_S = 0.15      # no documented limit: stay polite
RUZ_BATCH = 4                  # statements read per round (newest first)
RUZ_MAX_YEARS = 4              # statements ending before (this year - 4) are not used
_ruz_last = [0.0]
_templates: dict[int, dict[str, Any]] = {}

# key -> (table, description prefixes): first row whose description starts with a prefix.
# Lists of prefixes are alternatives (first match wins); "+" entries are summed.
RUZ_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "total_assets": ("A", ("spolu majetok",)),
    "fixed_assets": ("A", ("neobezny majetok",)),
    "current_assets": ("A", ("obezny majetok",)),
    "inventory": ("A", ("zasoby",)),
    "receivables": ("A", ("+dlhodobe pohladavky", "+kratkodobe pohladavky")),
    "cash": ("A", ("financne ucty", "financny majetok")),
    "equity": ("P", ("vlastne imanie",)),
    "share_capital": ("P", ("zakladne imanie",)),
    "debts": ("P", ("zavazky",)),
    "provisions": ("P", ("+dlhodobe rezervy", "+kratkodobe rezervy")),
    "turnover": ("V", ("cisty obrat", "+trzby z predaja tovaru", "+trzby z predaja vlastnych vyrobkov",
                       "+trzby z predaja sluzieb")),
    "total_revenue": ("V", ("+vynosy z hospodarskej cinnosti spolu", "+vynosy z financnej cinnosti spolu")),
    "gross_result": ("V", ("vysledok hospodarenia za uctovne obdobie pred zdanenim",)),
    "net_result": ("V", ("vysledok hospodarenia za uctovne obdobie po zdaneni",)),
}


def _ruz_get(url: str, timeout: float, retries: int = 2) -> Any:
    """GET + JSON; a dropped connection is retried twice (the server closes some under load)."""
    for attempt in range(retries + 1):
        wait = RUZ_MIN_INTERVAL_S * (1 + 4 * attempt) - (time.monotonic() - _ruz_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "SIAD-FidoSim/4.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:   # system proxy settings are used
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError):
            if attempt == retries:
                raise
        finally:
            _ruz_last[0] = time.monotonic()


def _table_kind(name: dict[str, str] | str) -> str | None:
    n = _norm(name.get("sk", "") if isinstance(name, dict) else name)
    if "aktiv" in n:
        return "A"
    if "pasiv" in n:
        return "P"
    if "ziskov" in n or "vysledovk" in n:
        return "V"
    return None


def _num(x: Any) -> float | None:
    if x is None:
        return None
    s = str(x).strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_ruz_report(report: dict[str, Any], template: dict[str, Any]) -> tuple[dict[str, float], list[list[Any]]]:
    """RÚZ report + its template -> ({field: value}, raw rows [table row, description, value]).

    The data of a table is a flat list read row by row; the number of columns is
    len(data) / number of rows. Current period: column 3 of 4 (brutto, korekcia, NETTO, previous)
    on the assets side, column 1 of 2 elsewhere.
    """
    tabs = {(_table_kind(t.get("nazov", {})) or str(i)): t for i, t in enumerate(template.get("tabulky", []))}
    data_tabs = {(_table_kind(t.get("nazov", {})) or str(i)): t for i, t in
                 enumerate(report.get("obsah", {}).get("tabulky", []))}
    rows: dict[str, list[tuple[str, str, float | None]]] = {}
    raw: list[list[Any]] = []
    for kind, tt in tabs.items():
        dt = data_tabs.get(kind)
        if dt is None or not tt.get("riadky"):
            continue
        data = dt.get("data", [])
        nrows = len(tt["riadky"])
        ncols = len(data) // nrows if nrows else 0
        if ncols <= 0:
            continue
        cur = 2 if ncols == 4 else 0
        lst = []
        for i, r in enumerate(tt["riadky"]):
            text = (r.get("text", {}) or {}).get("sk", "")
            val = _num(data[i * ncols + cur]) if i * ncols + cur < len(data) else None
            num = r.get("cisloRiadku")
            lst.append((str(num), text, val))
            raw.append([f"{kind}{num}", " ".join(x for x in (r.get("oznacenie"), text) if x).strip(), val])
        rows[kind] = lst
    values: dict[str, float] = {}
    for key, (kind, prefixes) in RUZ_FIELDS.items():
        lst = [(n, _norm(t), v) for n, t, v in rows.get(kind, [])]
        alt = [p for p in prefixes if not p.startswith("+")]
        add = [p[1:] for p in prefixes if p.startswith("+")]
        found = None
        for p in alt:
            hit = next((v for _n, t, v in lst if t.startswith(p)), "none")
            if hit != "none" and hit is not None:
                found = hit
                break
        if found is None and add:
            parts = [next((v for _n, t, v in lst if t.startswith(p)), None) for p in add]
            if any(x is not None for x in parts):
                found = sum(x for x in parts if x is not None)
        if found is not None:
            values[key] = float(found)
    # "B. Záväzky" includes the provisions (rezervy); ANAF's "Datorii" does not: same meaning everywhere
    if "debts" in values and values.get("provisions"):
        values["debts"] = values["debts"] - values["provisions"]
    net = values.pop("net_result", None)
    if net is not None:
        values["net_profit" if net >= 0 else "net_loss"] = abs(net)
    gross = values.pop("gross_result", None)
    if gross is not None:
        values["gross_profit" if gross >= 0 else "gross_loss"] = abs(gross)
    return values, raw


class RuzProvider(Provider):
    source = "ruz"
    automatic = True

    def _key(self, s: str) -> str | None:
        if re.fullmatch(r"\d{10}", s):          # DIČ / IČ DPH without "SK"
            return s
        if re.fullmatch(r"\d{6,8}", s):         # IČO
            return s.zfill(8)
        return None

    def search_url(self, key: str | None) -> str:
        return self.country.register_url

    def lookup(self, key: str, cache_dir: Path | None = None, refresh: bool = False,
               today: date | None = None, fetch: Fetch | None = None, timeout: float = 25.0) -> dict[str, Any]:
        fetch = fetch or _ruz_get
        cache = self.cache_path(key, cache_dir)
        if not refresh:
            hit = self.cached(key, cache_dir)
            if hit is not None:
                return hit
        field = "dic" if len(key) == 10 else "ico"
        res: dict[str, Any] = {"key": key, "cui": key, "source": "ruz", "status": "not_found", "years_tried": [],
                               "fetched_at": _now(), "url": self.search_url(key)}

        def get_(path: str) -> Any:
            return fetch(f"{RUZ_API}/{path}", timeout)

        try:
            ids = get_(f"uctovne-jednotky?zmenene-od=2000-01-01&{field}={key}").get("id", [])
            units = [u for u in (get_(f"uctovna-jednotka?id={i}") for i in ids) if not u.get("stav")]
            if not units:
                _write_cache(cache, res)
                res["from_cache"] = False
                return res
            units.sort(key=lambda u: (u.get("datumZrusenia") is None, len(u.get("idUctovnychZavierok", [])),
                                      u.get("datumPoslednejUpravy", "")), reverse=True)
            unit = units[0]
            res.update(name=(unit.get("nazovUJ") or "").strip(), unit_id=unit.get("id"),
                       caen_desc=f"SK NACE {unit['skNace']}" if unit.get("skNace") else None,
                       closed_on=unit.get("datumZrusenia"),
                       url=f"{RUZ_WEB}/accountingentity/show/{unit.get('id')}")
            # Statements are read newest first (higher id = filed later), a few at a time, until one
            # has structured data: a company with 25 years of filings needs a handful of calls, not 50.
            zids = sorted(unit.get("idUctovnychZavierok", []), reverse=True)
            stmts: list[dict[str, Any]] = []
            tried: set[int] = set()
            pdf_only: dict[str, Any] | None = None
            min_year = (today or date.today()).year - RUZ_MAX_YEARS
            for b in range(0, len(zids), RUZ_BATCH):
                batch = [z for z in (get_(f"uctovna-zavierka?id={i}") for i in zids[b:b + RUZ_BATCH])
                         if not z.get("stav") and z.get("obdobieDo")]
                if b and batch and max(int(z["obdobieDo"][:4]) for z in batch) < min_year:
                    break                       # older than anything useful for a credit decision
                stmts += batch
                # individual statements first (a consolidated one describes the group), latest period first
                stmts.sort(key=lambda z: (not z.get("konsolidovana"), z.get("obdobieDo", ""),
                                          z.get("typ") == "Riadna", z.get("datumPodania", "")), reverse=True)
                res["years_tried"] = sorted({int(z["obdobieDo"][:4]) for z in stmts}, reverse=True)[:6]
                for z in stmts:
                    if z["id"] in tried or int(z["obdobieDo"][:4]) < min_year:
                        continue
                    tried.add(z["id"])
                    found = self._read_statement(z, res, cache_dir, get_)
                    if found == "pdf" and pdf_only is None:
                        pdf_only = res.pop("_pdf")
                    if found == "ok":
                        break
                if res["status"] == "ok":
                    break
            if res["status"] == "ok" and pdf_only and pdf_only["period"] > res["period_end"]:
                res["note"] = "newer_pdf"
                res["newer_pdf"] = pdf_only
            if res["status"] != "ok" and (stmts or pdf_only):
                res["status"] = "no_data"
                if pdf_only:
                    res["newer_pdf"] = pdf_only
        except (urllib.error.URLError, OSError, ValueError, TimeoutError, KeyError) as e:
            res.update(status="error", error=str(getattr(e, "reason", e)))
            res["from_cache"] = False
            return res
        _write_cache(cache, res)
        res["from_cache"] = False
        return res

    def _read_statement(self, z: dict[str, Any], res: dict[str, Any], cache_dir: Path | None,
                        get_: Callable[[str], Any]) -> str:
        """'ok' (res filled), 'pdf' (only attachments: IFRS or scanned; res['_pdf']) or 'none'."""
        out = "none"
        for vid in z.get("idUctovnychVykazov", []):
            rep = get_(f"uctovny-vykaz?id={vid}")
            tabs = rep.get("obsah", {}).get("tabulky", [])
            if not tabs:
                if rep.get("prilohy") and out == "none" and "_pdf" not in res:
                    res["_pdf"] = {"period": z.get("obdobieDo"), "url": f"{RUZ_WEB}/financialreport/show/{vid}"}
                    out = "pdf"
                continue
            if rep.get("idSablony") is None:
                continue
            tpl = self._template(int(rep["idSablony"]), cache_dir, get_)
            kinds = {_table_kind(t.get("nazov", {})) for t in tpl.get("tabulky", [])}
            if not {"A", "P"} <= kinds:
                continue
            values, raw = parse_ruz_report(rep, tpl)
            if "equity" not in values:
                continue
            end = z["obdobieDo"]
            title = rep.get("obsah", {}).get("titulnaStrana", {})
            res.update(status="ok", year=int(end[:4]), period_end_month=int(end[5:7]), period_end=end,
                       period=f"{z.get('obdobieOd', '')} – {end}", template=tpl.get("nazov"),
                       consolidated=bool(z.get("konsolidovana")),
                       name=(title.get("nazovUctovnejJednotky") or res.get("name") or "").strip(),
                       values=values, raw=raw, currency=rep.get("mena") or "EUR",
                       report_url=f"{RUZ_WEB}/financialreport/show/{vid}")
            return "ok"
        return out

    def _template(self, sid: int, cache_dir: Path | None, get_: Callable[[str], Any]) -> dict[str, Any]:
        """Report templates never change: kept in memory and on disk."""
        if sid in _templates:
            return _templates[sid]
        path = Path(cache_dir) / f"ruz_template_{sid}.json" if cache_dir else None
        if path is not None and path.exists():
            try:
                _templates[sid] = json.loads(path.read_text(encoding="utf-8"))
                return _templates[sid]
            except (OSError, ValueError):
                pass
        tpl = get_(f"sablona?id={sid}")
        _templates[sid] = tpl
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        return tpl


# ---------------------------------------------------------------------------
# Austria, Czech Republic, Germany, Hungary: the register by hand, figures typed in
# ---------------------------------------------------------------------------
MANUAL_FIELDS = ("equity", "debts", "current_assets", "turnover", "net_result", "share_capital")


class ManualProvider(Provider):
    source = "manual"
    automatic = False

    def _key(self, s: str) -> str | None:
        if self.country.code == "HU":           # adószám 12345678-2-42: the first 8 digits (törzsszám)
            d = re.sub(r"\D", "", s)
            return d[:8] if len(d) >= 8 else None
        if self.country.code == "CZ":           # DIČ CZ12345678 = IČO for companies
            d = re.sub(r"\D", "", s)
            return d.zfill(8) if 6 <= len(d) <= 8 else (d if len(d) >= 4 else None)
        return s if len(s) >= 4 else None

    def lookup(self, key: str, cache_dir: Path | None = None, refresh: bool = False,
               today: date | None = None, fetch: Fetch | None = None) -> dict[str, Any]:
        hit = self.cached(key, cache_dir)
        return hit or {"key": key, "cui": key, "source": "manual", "status": "not_found", "years_tried": [],
                       "url": self.search_url(key)}

    def save(self, key: str, entered: dict[str, float | None], year: int, cache_dir: Path | None,
             name: str = "", note: str = "") -> dict[str, Any]:
        """Figures typed from the register (net_result is split into profit / loss like ANAF)."""
        values = {k: float(v) for k, v in entered.items() if v is not None and k != "net_result"}
        net = entered.get("net_result")
        if net is not None:
            values["net_profit" if net >= 0 else "net_loss"] = abs(float(net))
        res = {"key": key, "cui": key, "source": "manual", "status": "ok", "year": int(year),
               "period_end_month": 12, "name": name, "caen_desc": None, "values": values,
               "raw": [[k, k, entered.get(k)] for k in MANUAL_FIELDS if entered.get(k) is not None],
               "url": self.search_url(key), "years_tried": [int(year)], "fetched_at": _now(), "note": note,
               "entered": {k: entered.get(k) for k in MANUAL_FIELDS}}
        _write_cache(self.cache_path(key, cache_dir), res)
        res["from_cache"] = False
        return res

    def delete(self, key: str, cache_dir: Path | None) -> None:
        p = self.cache_path(key, cache_dir)
        if p is not None and p.exists():
            try:
                p.unlink()
            except OSError:
                pass


_PROVIDERS = {"anaf": AnafProvider, "ruz": RuzProvider, "manual": ManualProvider}


def for_country(code: str | None) -> Provider:
    c = get(code)
    return _PROVIDERS[c.balance_source](c)
