"""Read, recognise (by column signature), clean and match the three input files.

Public entry points: ``load_files(sources)`` and ``load_folder(path)``. Both return a
``LoadedData`` with tidy DataFrames (internal snake_case column names), the
Check fidi <-> Cerved matching (parameter independent) and data-quality findings.
"""
from __future__ import annotations

import io
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import country as _country

KIND_CHECKFIDI = "checkfidi"
KIND_CERVED = "cerved"
KIND_AR = "ar124"
KIND_MD105 = "md105"
KINDS = (KIND_CHECKFIDI, KIND_CERVED, KIND_AR)     # the three required inputs (``missing`` is about these)
OPTIONAL_KINDS = (KIND_MD105,)                   # optional (recommended): JDE customer master, opening date
ALL_KINDS = KINDS + OPTIONAL_KINDS

SEV_ERROR, SEV_WARNING, SEV_INFO = "error", "warning", "info"

# What cannot be computed when a file is missing (keys for texts.py).
UNAVAILABLE_IF_MISSING: dict[str, list[str]] = {
    KIND_CHECKFIDI: ["everything"],
    KIND_CERVED: ["cerved_score", "cerved_ceiling", "plausibility"],
    KIND_AR: ["payment_days_measured", "contract_terms", "default_reference_date"],
}


class LoaderError(ValueError):
    """A recognised file cannot be used (e.g. a required column is missing)."""


@dataclass
class Finding:
    """One data-quality observation. ``code`` is a key of texts.DQ_TEXTS."""
    code: str
    severity: str
    count: int
    examples: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Column specifications: canonical internal name -> source header (normalised)
# ---------------------------------------------------------------------------
def _norm_header(h: Any) -> str:
    """Lower case, newlines and repeated spaces collapsed: 'Customer\\nNumber' -> 'customer number'."""
    return re.sub(r"\s+", " ", str(h)).strip().lower()


CF_COLS = {  # internal: (source header, required[, feature disabled when the optional column is missing])
    "code": ("Code", True), "name": ("Name", True), "company_code": ("Company Code", False),
    "company": ("Company", False), "balance": ("Balance", True), "current": ("Current", False),
    "overdue": ("Overdue", True), "ordered": ("Ordered", True), "delivered": ("Delivered", True),
    "credit_limit": ("Credit Limit", True), "fill_pct": ("% Fill", False),
    "risk_class": ("Code  Risk Class (AMF)", True), "doris_code": ("Code  Cod. DORIS", False),
    "block_description": ("Block Description", False),
    "turnover_12m": ("Turnover 12 months", True), "vat": ("VAT", False, "vat_matching"),
}
CV_COLS = {
    "code_raw": ("RIFERIMENTO", True), "vat": ("PARTITA_IVA", False, "vat_matching"),
    "name": ("RAGIONE_SOCIALE", False), "score": ("SCORE SEMAFORICO", True),
    "cerved_limit": ("VALORE_FIDO", True), "currency": ("VALUTA", False, "currency"),
    "reliability_class": ("CLASSE_AFFIDABILITA", False, "reliability_class"),
    "total_turnover": ("FATTURATO_NO_BIL", False, "plausibility"),
    "payment_habits": ("ABITUDINI_PAGAMENTO", False),
}
AR_COLS = {
    "customer": ("Customer Number", True), "document": ("Document Number", False),
    "name": ("Name Alpha", False), "tax_id": ("Tax ID", False),
    "invoice_date": ("Invoice Date", True), "due_date": ("Due Date", True),
    "amount": ("Gross Amount", True), "closed_date": ("Date Invoice Closed", True),
}
MD_COLS = {  # JDE customer master MD105 (sheet "MD105.Customer Master", title row 1, header row 2)
    "customer": ("Cliente", True), "name": ("Descrizione Cliente", False), "status": ("Stato Cliente", False),
    "tax_id": ("Tax ID", False), "payment_terms": ("Payment Terms - A/R", False),
    "opened_date": ("Date - Account Opened", True),
}
SPECS = {KIND_CHECKFIDI: CF_COLS, KIND_CERVED: CV_COLS, KIND_AR: AR_COLS, KIND_MD105: MD_COLS}
# Signature = headers that identify the kind (a subset of the required ones).
SIGNATURES = {
    KIND_CHECKFIDI: {"credit limit", "turnover 12 months", "code risk class (amf)"},
    KIND_CERVED: {"riferimento", "score semaforico", "valore_fido"},
    KIND_AR: {"customer number", "gross amount", "date invoice closed"},
    KIND_MD105: {"cliente", "date - account opened", "descrizione cliente"},
}
HEADER_ROWS = (0, 1, 2)   # header row tried in order (MD105 has a title on row 1, the header on row 2)
SCORES = ("AFFIDABILE", "CAUTELA", "MASSIMA CAUTELA")
def local_currency() -> str:
    """Currency of the active country: Cerved limits in it are used as they are (EUR converted at eur_rate)."""
    return _country.currency()


def known_currencies() -> tuple[str, ...]:
    return tuple(dict.fromkeys((local_currency(), "EUR")))


def detect_kind(columns: Iterable[Any]) -> str | None:
    """Return the kind with the most signature columns present (at least 2 of 3), else None.

    Requiring only 2 of 3 lets a file with one missing key column still be recognised,
    so the user gets a precise "column X is missing" message instead of "not recognised".
    """
    cols = {_norm_header(c) for c in columns}
    best, hits = None, 1
    for kind, sig in SIGNATURES.items():
        n = len(sig & cols)
        if n > hits:
            best, hits = kind, n
    return best


def _select_columns(df: pd.DataFrame, kind: str, file_name: str,
                    findings: list[Finding] | None = None) -> pd.DataFrame:
    """Rename source headers to internal names.

    A missing required column raises LoaderError (listing all of them). A missing optional
    column becomes NaN; if it feeds a feature, a COLUMN_MISSING finding says which feature
    is disabled (``details["unavailable"]`` = keys of texts.UNAVAILABLE_TEXTS).
    """
    by_norm = {_norm_header(c): c for c in df.columns}
    out, missing, optional_missing, features = {}, [], [], []
    for internal, spec in SPECS[kind].items():
        header, required = spec[0], spec[1]
        feature = spec[2] if len(spec) > 2 else None
        src = by_norm.get(_norm_header(header))
        if src is None:
            if required:
                missing.append(header.replace("\n", " "))
            elif feature:
                optional_missing.append(header)
                if feature not in features:
                    features.append(feature)
            out[internal] = pd.Series(np.nan, index=df.index, dtype=object)
        else:
            out[internal] = df[src]
    if missing:
        raise LoaderError(
            f"File '{file_name}' looks like {kind} but required column(s) are missing: "
            + ", ".join(repr(m) for m in missing)
            + ". Columns found: " + ", ".join(repr(str(c)) for c in df.columns[:30]))
    if optional_missing and findings is not None:
        findings.append(Finding("COLUMN_MISSING", SEV_WARNING, len(optional_missing), optional_missing,
                                {"kind": kind, "columns": optional_missing, "unavailable": features}))
    return pd.DataFrame(out, index=df.index)


# ---------------------------------------------------------------------------
# Small cleaning helpers
# ---------------------------------------------------------------------------
def code_to_str(x: Any) -> str | None:
    """Customer code as a clean string, the same in all three files.

    Spaces are stripped; numeric codes are compared by their integer value, so
    30001539, 30001539.0, '30001539.0', ' 0030001539 ' -> '30001539'. Other codes stay as text.
    """
    if x is None or x is pd.NA or x is pd.NaT:
        return None
    if isinstance(x, (bool, np.bool_)):
        return None
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        if np.isnan(x):
            return None
        return str(int(x)) if float(x).is_integer() else str(x)
    s = re.sub(r"\s+", "", str(x))
    if re.fullmatch(r"\d+(\.0*)?", s):
        s = str(int(s.split(".")[0]))
    return s or None


def normalize_vat(x: Any) -> str | None:
    """VAT key: letters and digits only, upper case, the active country's prefix removed
    ('RO 14697790' -> '14697790' for Romania, 'SK2020123456' -> '2020123456' for Slovakia)."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or x is pd.NA:
        return None
    s = re.sub(r"[^A-Z0-9]", "", str(x).upper())
    s = _country.strip_vat_prefix(s)
    return s or None


_MINUS = "−‒–—"            # unicode minus signs / dashes
_SPACES = re.compile(r"[\s   ']+")  # spaces, NBSP, thin spaces, apostrophe (CH)
_NUMBER = re.compile(r"\d+(\.\d+)?")


THOUSANDS = "thousands"   # pseudo decimal char: both '.' and ',' are thousands separators
_AMBIG = re.compile(r"[^.,]*\d[.,]\d{3}")  # one separator followed by exactly 3 digits: '12.500', '120,000'


def _decimal_char(texts: list[str], amounts: bool = False) -> tuple[str | None, bool]:
    """Infer the decimal separator of a text column: ('.' / ',' / None, ambiguous).

    Evidence, strongest first: a value with both separators (the last one is the decimal);
    a separator appearing more than once in a value (thousands); a single separator not
    followed by exactly 3 digits (decimal). With no evidence at all, every value with a
    separator looks like '12.500' or '120,000' and the column is *ambiguous*: in amount columns
    the separator is read as thousands (``THOUSANDS``: a JDE / CreditBoard amount of 12.5 RON
    written '12.500' is far less likely than 12,500 RON); elsewhere a single ',' is a decimal
    comma and a single '.' a decimal point (the old rule).
    """
    votes = {".": 0, ",": 0}
    has = {".": False, ",": False}
    for t in texts:
        d, c = t.count("."), t.count(",")
        has["."] |= d > 0
        has[","] |= c > 0
        if d and c:
            votes["." if t.rfind(".") > t.rfind(",") else ","] += 10
        elif d > 1:
            votes[","] += 5
        elif c > 1:
            votes["."] += 5
        elif d == 1 and not re.search(r"\.\d{3}$", t):
            votes["."] += 1
        elif c == 1 and not re.search(r",\d{3}$", t):
            votes[","] += 1
    if votes["."] or votes[","]:
        return ("." if votes["."] >= votes[","] else ","), False
    if not (has["."] or has[","]):
        return None, False
    if amounts:
        return THOUSANDS, True
    return ("," if has[","] else "."), True


def _parse_text_number(t: str, dec: str | None) -> float:
    neg = False
    t = _SPACES.sub("", t)
    for m in _MINUS:
        t = t.replace(m, "-")
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    if t.endswith("-"):
        neg, t = not neg, t[:-1]
    if t.startswith("-"):
        neg, t = not neg, t[1:]
    elif t.startswith("+"):
        t = t[1:]
    if "." in t and "," in t:                 # unambiguous: the last separator is the decimal one
        dec = "." if t.rfind(".") > t.rfind(",") else ","
    elif t.count(".") > 1:
        dec = ","
    elif t.count(",") > 1:
        dec = "."
    if dec == THOUSANDS:
        t = t.replace(".", "").replace(",", "")
    elif dec == ",":
        t = t.replace(".", "").replace(",", ".")
    elif dec == ".":
        t = t.replace(",", "")
    if not _NUMBER.fullmatch(t):
        return np.nan
    v = float(t)
    return -v if neg else v


def parse_numbers(s: pd.Series, amounts: bool = False) -> tuple[pd.Series, pd.Series]:
    """Numbers from a column that may hold text ('12.500,00', '12,500.00', ' -1 200 ', '(50)').

    Returns (float values with NaN for blanks and failures, mask of non-blank values that
    could not be read). Real numbers are kept as they are. ``amounts=True``: a column whose
    only separators look like '12.500' / '120,000' is read with thousands separators
    (see ``parse_numbers_ex`` for the mask of those ambiguous values).
    """
    v, failed, _amb = parse_numbers_ex(s, amounts)
    return v, failed


def parse_numbers_ex(s: pd.Series, amounts: bool = False) -> tuple[pd.Series, pd.Series, pd.Series]:
    """``parse_numbers`` plus the mask of values whose separator was ambiguous in the column."""
    none = pd.Series(False, index=s.index)
    if pd.api.types.is_numeric_dtype(s.dtype) and not pd.api.types.is_bool_dtype(s.dtype):
        return s.astype(float), none, none
    vals = s.astype(object)
    is_text = vals.map(lambda x: isinstance(x, str))
    texts = vals[is_text].map(str.strip)
    texts = texts[texts != ""]
    dec, ambiguous = _decimal_char(texts.tolist(), amounts)
    cache: dict[str, float] = {}

    def conv(x: Any) -> float:
        if x is None or x is pd.NA or isinstance(x, (bool, np.bool_)):
            return np.nan
        if isinstance(x, (int, float, np.integer, np.floating)):
            return float(x)
        if isinstance(x, str):
            t = x.strip()
            if not t:
                return np.nan
            if t not in cache:
                cache[t] = _parse_text_number(t, dec)
            return cache[t]
        return np.nan
    out = vals.map(conv).astype(float)
    blank = vals.map(lambda x: x is None or x is pd.NA or (isinstance(x, float) and np.isnan(x))
                     or (isinstance(x, str) and not x.strip()))
    amb = none
    if ambiguous:
        amb = vals.map(lambda x: isinstance(x, str) and _AMBIG.fullmatch(_SPACES.sub("", x.strip())) is not None)
        amb = amb.astype(bool) & out.notna()
    return out, out.isna() & ~blank.astype(bool), amb


def _num(s: pd.Series, fill: float | None = 0.0, bad: dict[str, Any] | None = None,
         col: str = "", amb: dict[str, Any] | None = None) -> pd.Series:
    """Robust numbers; values that cannot be read are counted in ``bad`` (col -> [n, examples]).

    With ``amb`` the column is an amount column: ambiguous separators ('12.500') are read as
    thousands and counted in ``amb`` (same shape as ``bad``)."""
    v, failed, ambiguous = parse_numbers_ex(s, amounts=amb is not None)
    for store, mask in ((bad, failed), (amb, ambiguous)):
        if store is not None and mask.any():
            n, ex = store.setdefault(col, [0, []])
            store[col][0] = n + int(mask.sum())
            ex.extend(str(x) for x in s[mask].head(5 - len(ex)).tolist())
    return v.fillna(fill) if fill is not None else v


def _text(s: pd.Series) -> pd.Series:
    """Stripped strings, NaN kept as NaN (object dtype for pandas 2/3 compatibility)."""
    return s.map(lambda x: np.nan if pd.isna(x) else (str(x).strip() or np.nan)).astype(object)


_ISO_DATE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}([ T].*)?")
_DAYFIRST_FORMATS = ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y", "%d-%m-%y",
                     "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
_EXCEL_EPOCH = pd.Timestamp("1899-12-30")


def _parse_text_date(t: str) -> pd.Timestamp | None:
    """Text date, European day-first (03/02/2026 = 3 February); ISO yyyy-mm-dd also accepted."""
    from datetime import datetime
    t = t.strip()
    if _ISO_DATE.fullmatch(t):
        try:
            return pd.Timestamp(t)
        except (ValueError, OverflowError):
            return None
    date_part, _, time_part = t.partition(" ")
    for fmt in _DAYFIRST_FORMATS:
        try:
            d = datetime.strptime(date_part, fmt)
        except ValueError:
            continue
        ts = pd.Timestamp(d)
        if time_part:
            try:
                ts = ts + (pd.Timestamp("2000-01-01 " + time_part.strip()) - pd.Timestamp("2000-01-01"))
            except (ValueError, OverflowError):
                pass
        return ts
    return None


_EXCEL_SERIAL_MAX = 106_750       # pd.Timedelta overflows at ~106.751 days: larger serials are not dates


def _is_julian(v: float) -> bool:
    """JDE Julian date CYYDDD (C = century after 1900, DDD = day of the year): 126001 = 01/01/2026."""
    if not float(v).is_integer() or v < 1:
        return False
    c_yy, ddd = divmod(int(v), 1000)
    return 0 <= c_yy <= 199 and 1 <= ddd <= 366


def _julian(v: float) -> Any:
    c_yy, ddd = divmod(int(v), 1000)
    year = 1900 + c_yy
    days_in_year = 366 if pd.Timestamp(year=year, month=12, day=31).dayofyear == 366 else 365
    if ddd > days_in_year:
        return pd.NaT
    return pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=ddd - 1)


def parse_dates(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Dates from a column: real Excel dates unchanged; text day-first; numbers.

    Numbers are Excel serial days (1 .. 106.749), except when the column looks like JDE Julian
    dates (CYYDDD, e.g. 126001 = 01/01/2026): every number is a valid CYYDDD and at least one is
    from 2000 on (>= 100.000), then all are decoded as Julian dates. Numbers that are neither give
    a blank date counted in the "not readable" mask (never an error).
    Returns (datetime64[ns] values, mask of non-blank values that could not be read).
    """
    if pd.api.types.is_datetime64_any_dtype(s.dtype):
        return s.astype("datetime64[ns]"), pd.Series(False, index=s.index)
    obj = s.astype(object)
    nums = [float(x) for x in obj if isinstance(x, (int, float, np.integer, np.floating))
            and not isinstance(x, (bool, np.bool_)) and not np.isnan(float(x))]
    julian = bool(nums) and all(_is_julian(v) for v in nums) and any(v >= 100_000 for v in nums)
    cache: dict[str, Any] = {}

    def conv(x: Any) -> Any:
        if x is None or x is pd.NA or x is pd.NaT:
            return pd.NaT
        if isinstance(x, (pd.Timestamp, np.datetime64)) or hasattr(x, "year"):
            try:
                return pd.Timestamp(x)
            except (ValueError, TypeError, OverflowError):
                return pd.NaT
        if isinstance(x, (bool, np.bool_)):
            return pd.NaT
        if isinstance(x, (int, float, np.integer, np.floating)):
            v = float(x)
            if np.isnan(v):
                return pd.NaT
            try:
                if julian:
                    return _julian(v)
                if 1 <= v < _EXCEL_SERIAL_MAX:                  # Excel serial day number
                    return _EXCEL_EPOCH + pd.Timedelta(days=v)
            except (ValueError, OverflowError):
                pass
            return pd.NaT
        t = str(x).strip()
        if not t:
            return pd.NaT
        if t not in cache:
            cache[t] = _parse_text_date(t)
        return cache[t] if cache[t] is not None else pd.NaT
    vals = obj.map(conv)
    out = pd.to_datetime(vals, errors="coerce").astype("datetime64[ns]")
    blank = obj.map(lambda x: x is None or x is pd.NA or x is pd.NaT
                    or (isinstance(x, float) and np.isnan(x))
                    or (isinstance(x, str) and not x.strip()))
    return out, out.isna() & ~blank.astype(bool)


def _dates(s: pd.Series, bad: dict[str, Any] | None = None, col: str = "") -> pd.Series:
    v, failed = parse_dates(s)
    if bad is not None and failed.any():
        n, ex = bad.setdefault(col, [0, []])
        bad[col][0] = n + int(failed.sum())
        ex.extend(str(x) for x in s[failed].head(5 - len(ex)).tolist())
    return v


def _bad_finding(code: str, bad: dict[str, Any], kind: str) -> list[Finding]:
    """One BAD_NUMBERS / BAD_DATES / AMBIGUOUS_NUMBERS finding for a file (count = values concerned)."""
    if not bad:
        return []
    total = sum(v[0] for v in bad.values())
    examples = [f"{c}: {e}" for c, (_n, ex) in bad.items() for e in ex][:10]
    return [Finding(code, SEV_WARNING, total, examples,
                    {"kind": kind, "columns": {c: v[0] for c, v in bad.items()}})]


# ---------------------------------------------------------------------------
# Cleaning per kind
# ---------------------------------------------------------------------------
def _hdr(kind: str, internal: str) -> str:
    return SPECS[kind][internal][0]


def clean_checkfidi(raw: pd.DataFrame, file_name: str = "checkfidi") -> tuple[pd.DataFrame, list[Finding]]:
    """Tidy Check fidi: code string, amounts NaN->0, risk class stripped, VAT normalised.

    If the file holds more than one Company Code, only the most frequent company is kept
    (CF_MULTI_COMPANY finding); duplicated codes inside that company keep the first row.
    """
    findings: list[Finding] = []
    df = _select_columns(raw, KIND_CHECKFIDI, file_name, findings)
    if df.empty:
        findings.append(Finding("FILE_EMPTY", SEV_WARNING, 1, [file_name], {"kind": KIND_CHECKFIDI}))
    df["code"] = df["code"].map(code_to_str).astype(object)
    nocode = df["code"].isna().to_numpy(bool)
    if nocode.any():
        findings.append(Finding("CF_NO_CODE", SEV_WARNING, int(nocode.sum())))
        df = df.loc[~nocode]
    df["company_code"] = df["company_code"].map(code_to_str).astype(object)
    companies = df["company_code"].dropna().value_counts(sort=False)
    if len(companies) > 1:
        # most frequent company; ties -> the one that appears first in the file
        order = {c: i for i, c in enumerate(df["company_code"].dropna().unique())}
        kept = sorted(companies.index, key=lambda c: (-companies[c], order[c]))[0]
        drop = (df["company_code"].notna() & (df["company_code"] != kept)).to_numpy(bool)
        names = df.groupby("company_code")["company"].first()
        both = sorted(set(df.loc[drop, "code"]) & set(df.loc[~drop, "code"]))
        findings.append(Finding(
            "CF_MULTI_COMPANY", SEV_WARNING, int(drop.sum()),
            [f"{c} {names.get(c) if isinstance(names.get(c), str) else ''}".strip() + f": {int(companies[c])}"
             for c in sorted(companies.index, key=lambda c: -companies[c])],
            {"kept": kept, "kept_name": names.get(kept) if isinstance(names.get(kept), str) else "",
             "companies": {str(c): int(n) for c, n in companies.items()},
             "codes_in_several_companies": len(both), "codes_examples": both[:10]}))
        df = df.loc[~drop]
    missing_limit = df["credit_limit"].isna().to_numpy(bool)
    if missing_limit.any():
        findings.append(Finding("CF_LIMIT_BLANK", SEV_INFO, int(missing_limit.sum()),
                                df.loc[missing_limit, "code"].head(10).tolist()))
    bad: dict[str, Any] = {}
    amb: dict[str, Any] = {}
    for c in ("balance", "current", "overdue", "ordered", "delivered", "credit_limit",
              "fill_pct", "turnover_12m"):
        df[c] = _num(df[c], bad=bad, col=_hdr(KIND_CHECKFIDI, c), amb=None if c == "fill_pct" else amb)
    findings += _bad_finding("BAD_NUMBERS", bad, KIND_CHECKFIDI)
    findings += _bad_finding("AMBIGUOUS_NUMBERS", amb, KIND_CHECKFIDI)
    for c in ("name", "company", "doris_code", "block_description", "vat"):
        df[c] = _text(df[c])
    df["risk_class"] = _text(df["risk_class"]).fillna("").str.upper().astype(object)
    df["vat_norm"] = df["vat"].map(normalize_vat).astype(object)
    dup = df["code"].duplicated(keep="first").to_numpy(bool)
    if dup.any():
        findings.append(Finding("CF_DUP_CODE", SEV_WARNING, int(dup.sum()),
                                df.loc[dup, "code"].head(10).tolist()))
        df = df.loc[~dup]
    return df.reset_index(drop=True), findings


def clean_cerved(raw: pd.DataFrame, file_name: str = "cerved") -> tuple[pd.DataFrame, list[Finding]]:
    """Tidy Cerved: code = str(int(RIFERIMENTO)); VALORE_FIDO NaN kept (NaN = no suggested limit).

    ``limit_usable`` says whether VALORE_FIDO can be a ceiling: valorised, >= 0 and in RON,
    EUR or blank currency (blank = RON). Other currencies and negative values give no ceiling
    (findings CV_OTHER_CURRENCY / CV_NEGATIVE_LIMIT).
    """
    findings: list[Finding] = []
    df = _select_columns(raw, KIND_CERVED, file_name, findings)
    if df.empty:
        findings.append(Finding("FILE_EMPTY", SEV_WARNING, 1, [file_name], {"kind": KIND_CERVED}))
    df.insert(0, "cv_row", np.arange(len(df)))
    df["code"] = df["code_raw"].map(code_to_str).astype(object)
    df = df.drop(columns="code_raw")
    for c in ("vat", "name"):
        df[c] = _text(df[c])
    df["vat_norm"] = df["vat"].map(normalize_vat).astype(object)
    df["score"] = _text(df["score"]).str.upper().astype(object)
    df["currency"] = _text(df["currency"]).str.upper().astype(object)
    bad: dict[str, Any] = {}
    amb: dict[str, Any] = {}
    df["cerved_limit"] = _num(df["cerved_limit"], None, bad, "VALORE_FIDO", amb)          # NaN = not valorised
    df["total_turnover"] = _num(df["total_turnover"], None, bad, "FATTURATO_NO_BIL", amb)  # NaN = unknown
    df["reliability_class"] = _num(df["reliability_class"], None, bad, "CLASSE_AFFIDABILITA")
    df["payment_habits"] = _num(df["payment_habits"], None, bad, "ABITUDINI_PAGAMENTO")
    findings += _bad_finding("BAD_NUMBERS", bad, KIND_CERVED)
    findings += _bad_finding("AMBIGUOUS_NUMBERS", amb, KIND_CERVED)

    nocode = df["code"].isna()
    if nocode.any():
        findings.append(Finding("CV_NO_CODE", SEV_INFO, int(nocode.sum()),
                                df.loc[nocode, "name"].fillna("?").head(10).tolist()))
    coded = df[~nocode.to_numpy(bool)]
    dmask = coded["code"].duplicated(keep=False)
    if dmask.any():
        dups = coded[dmask.to_numpy(bool)]
        diff_company = dups.groupby("code")["vat_norm"].nunique(dropna=True)
        diff_company = sorted(diff_company[diff_company > 1].index.tolist())
        codes = sorted(dups["code"].unique().tolist())
        findings.append(Finding(
            "CV_DUP_CODE", SEV_WARNING, len(codes), codes[:20],
            {"rows": int(dmask.sum()), "codes_with_different_vat": diff_company}))
    has_lim = df["cerved_limit"].notna()
    label = lambda m: [f"{c or '-'} {n}" for c, n in df.loc[m, ["code", "name"]].fillna("").values][:10]  # noqa: E731
    eur = df["currency"].eq("EUR") & has_lim & (local_currency() != "EUR")
    if eur.any():
        findings.append(Finding("CV_EUR_LIMIT", SEV_INFO, int(eur.sum()), label(eur)))
    nocur = df["currency"].isna() & has_lim
    if nocur.any():
        findings.append(Finding("CV_NO_CURRENCY", SEV_INFO, int(nocur.sum()),
                                df.loc[nocur, "code"].fillna("?").head(10).tolist(),
                                {"assumed": local_currency()}))
    other = df["currency"].notna() & ~df["currency"].isin(known_currencies()) & has_lim
    if other.any():
        findings.append(Finding("CV_OTHER_CURRENCY", SEV_WARNING, int(other.sum()), label(other),
                                {"currencies": ", ".join(sorted(df.loc[other, "currency"].unique().tolist()))}))
    neg = has_lim & (df["cerved_limit"] < 0)
    if neg.any():
        findings.append(Finding("CV_NEGATIVE_LIMIT", SEV_WARNING, int(neg.sum()), label(neg)))
    df["limit_usable"] = (has_lim & ~other & ~neg).astype(bool)
    unknown = ~df["score"].isna() & ~df["score"].isin(SCORES)
    if unknown.any():
        findings.append(Finding("CV_UNKNOWN_SCORE", SEV_WARNING, int(unknown.sum()),
                                sorted(df.loc[unknown, "score"].unique().tolist())[:10]))
    return df.reset_index(drop=True), findings


_DIGITS = re.compile(r"\d+")


def clean_ar(raw: pd.DataFrame, file_name: str = "ar124") -> tuple[pd.DataFrame, list[Finding]]:
    """Tidy AR124: drop total rows (customer not fully numeric), dates parsed, amount NaN->0.

    A file with the headers and no rows is valid (no invoices: FILE_EMPTY finding).
    """
    findings: list[Finding] = []
    df = _select_columns(raw, KIND_AR, file_name, findings)
    if df.empty:
        findings.append(Finding("FILE_EMPTY", SEV_WARNING, 1, [file_name], {"kind": KIND_AR}))
    cust = df["customer"].map(code_to_str)
    keep = np.array([bool(c) and _DIGITS.fullmatch(c) is not None for c in cust], dtype=bool)
    n_drop = int((~keep).sum())
    if n_drop:
        findings.append(Finding("AR_TOTAL_ROWS_DROPPED", SEV_INFO, n_drop,
                                df.loc[~keep, "customer"].astype(str).head(5).tolist()))
    df = df.loc[keep].copy()
    df["customer"] = cust[keep].astype(object)
    bad_d: dict[str, Any] = {}
    for c in ("invoice_date", "due_date", "closed_date"):
        df[c] = _dates(df[c], bad_d, _hdr(KIND_AR, c))
    findings += _bad_finding("BAD_DATES", bad_d, KIND_AR)
    bad_n: dict[str, Any] = {}
    amb_n: dict[str, Any] = {}
    df["amount"] = _num(df["amount"], bad=bad_n, col=_hdr(KIND_AR, "amount"), amb=amb_n)
    findings += _bad_finding("BAD_NUMBERS", bad_n, KIND_AR)
    findings += _bad_finding("AMBIGUOUS_NUMBERS", amb_n, KIND_AR)
    df["document"] = df["document"].map(code_to_str).astype(object)
    for c in ("name", "tax_id"):
        df[c] = _text(df[c])
    bad = df["invoice_date"].isna().to_numpy(bool)
    if bad.any():
        findings.append(Finding("AR_NO_INVOICE_DATE", SEV_WARNING, int(bad.sum()),
                                df.loc[bad, "customer"].head(10).tolist()))
    return df.reset_index(drop=True), findings


def clean_md105(raw: pd.DataFrame, file_name: str = "md105") -> tuple[pd.DataFrame, list[Finding]]:
    """Tidy JDE customer master MD105 (optional file): customer code (same normalisation as the other
    files), name, status, Tax ID, payment terms (kept, not used yet), account opening date.

    Rows without a code are dropped (MD_NO_CODE); a code listed twice keeps its EARLIEST opening date
    (MD_DUP_CODE). Unreadable dates -> NaT + BAD_DATES. 31/08/2006 is the JDE migration date (accounts
    opened before 2006): it is used as it is (an old, consolidated customer).
    """
    findings: list[Finding] = []
    df = _select_columns(raw, KIND_MD105, file_name, findings)
    if df.empty:
        findings.append(Finding("FILE_EMPTY", SEV_WARNING, 1, [file_name], {"kind": KIND_MD105}))
    df["customer"] = df["customer"].map(code_to_str).astype(object)
    nocode = df["customer"].isna().to_numpy(bool)
    if nocode.any():
        findings.append(Finding("MD_NO_CODE", SEV_WARNING, int(nocode.sum())))
        df = df.loc[~nocode].copy()
    bad_d: dict[str, Any] = {}
    df["opened_date"] = _dates(df["opened_date"], bad_d, _hdr(KIND_MD105, "opened_date"))
    findings += _bad_finding("BAD_DATES", bad_d, KIND_MD105)
    for c in ("name", "status", "tax_id", "payment_terms"):
        df[c] = _text(df[c])
    dup = df["customer"].duplicated(keep=False).to_numpy(bool)
    if dup.any():
        findings.append(Finding("MD_DUP_CODE", SEV_INFO, int(df.loc[dup, "customer"].nunique()),
                                df.loc[dup, "customer"].drop_duplicates().head(10).tolist()))
        df = df.sort_values(["customer", "opened_date"], kind="mergesort", na_position="last")
        df = df.drop_duplicates("customer", keep="first")
    return df.reset_index(drop=True), findings


CLEANERS = {KIND_CHECKFIDI: clean_checkfidi, KIND_CERVED: clean_cerved, KIND_AR: clean_ar,
            KIND_MD105: clean_md105}


# ---------------------------------------------------------------------------
# Matching Check fidi <-> Cerved (parameter independent)
# ---------------------------------------------------------------------------
CV_FIELDS = ["cv_row", "cv_code", "cv_name", "cv_vat", "cv_vat_norm", "score", "cerved_limit",
             "currency", "limit_usable", "reliability_class", "total_turnover", "payment_habits"]


def match_cerved(cf: pd.DataFrame, cv: pd.DataFrame | None, reject_vat_conflict: bool = True) -> pd.DataFrame:
    """Add Cerved fields to Check fidi rows.

    1) by code (Code == str(int(RIFERIMENTO))). A Cerved row whose normalised VAT is present and
       differs from the (present) Check fidi VAT is a *VAT conflict*: with ``reject_vat_conflict``
       (default, lead decision) it is never used. Among the remaining rows with that code prefer
       the one with the same VAT, otherwise the first in file order;
    2) customers still unmatched: by normalised VAT, first Cerved row with that VAT.
    Adds ``match_method`` ('code' / 'vat' / NaN), ``vat_differs`` (code match kept although the
    VATs differ: only with ``reject_vat_conflict=False``), ``vat_conflict`` (a code match was
    rejected for a different VAT) and ``conflict_cv_name`` / ``conflict_cv_vat`` (that Cerved row).
    """
    out = cf.copy()
    for c in CV_FIELDS:
        out[c] = np.nan
    out["match_method"] = np.nan
    out["vat_differs"] = False
    out["vat_conflict"] = False
    out["conflict_cv_name"] = np.nan
    out["conflict_cv_vat"] = np.nan
    for c in CV_FIELDS + ["match_method", "conflict_cv_name", "conflict_cv_vat"]:
        out[c] = out[c].astype(object)
    if cv is None or cv.empty:
        return _fix_match_dtypes(out)

    cvr = cv.rename(columns={"code": "cv_code", "name": "cv_name", "vat": "cv_vat",
                             "vat_norm": "cv_vat_norm"})
    if "limit_usable" not in cvr:
        cvr["limit_usable"] = cvr["cerved_limit"].notna()
    cvr = cvr[CV_FIELDS]
    left = out[["code", "vat_norm"]].reset_index().rename(columns={"index": "cf_idx"})
    m = left.merge(cvr[cvr["cv_code"].notna()], left_on="code", right_on="cv_code", how="inner")
    both = m["vat_norm"].notna() & m["cv_vat_norm"].notna()
    m["vat_eq"] = both & (m["vat_norm"] == m["cv_vat_norm"])
    m["conflict"] = both & ~m["vat_eq"]
    conflicts = m[m["conflict"]].sort_values(["cf_idx", "cv_row"], kind="mergesort") \
        .drop_duplicates("cf_idx", keep="first").set_index("cf_idx")
    if reject_vat_conflict:
        m = m[~m["conflict"]]
    m = m.sort_values(["cf_idx", "vat_eq", "cv_row"], ascending=[True, False, True], kind="mergesort")
    m = m.drop_duplicates("cf_idx", keep="first").set_index("cf_idx")
    m["match_method"] = "code"
    conflicts = conflicts[~conflicts.index.isin(m.index)]   # only customers left without a code match

    un = left[~left["cf_idx"].isin(m.index) & left["vat_norm"].notna()]
    byvat = cvr[cvr["cv_vat_norm"].notna()].sort_values("cv_row", kind="mergesort") \
        .drop_duplicates("cv_vat_norm", keep="first")
    v = un.merge(byvat, left_on="vat_norm", right_on="cv_vat_norm", how="inner").set_index("cf_idx")
    v["match_method"] = "vat"

    for part in (m, v):
        if len(part):
            for c in CV_FIELDS + ["match_method"]:
                out.loc[part.index, c] = part[c].values
    code_m = out["match_method"].eq("code")
    out["vat_differs"] = code_m & out["vat_norm"].notna() & out["cv_vat_norm"].notna() \
        & (out["vat_norm"] != out["cv_vat_norm"])
    if reject_vat_conflict and len(conflicts):
        out.loc[conflicts.index, "vat_conflict"] = True
        out.loc[conflicts.index, "conflict_cv_name"] = conflicts["cv_name"].values
        out.loc[conflicts.index, "conflict_cv_vat"] = conflicts["cv_vat"].values
    return _fix_match_dtypes(out)


def _fix_match_dtypes(out: pd.DataFrame) -> pd.DataFrame:
    for c in ("cv_row", "cerved_limit", "reliability_class", "total_turnover", "payment_habits"):
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)
    out["in_cerved"] = out["match_method"].notna()
    out["limit_usable"] = out["limit_usable"].map(lambda x: bool(x) if isinstance(x, (bool, np.bool_)) else False)
    out["limit_usable"] = out["limit_usable"].astype(bool) & out["in_cerved"]
    for c in ("vat_differs", "vat_conflict"):
        out[c] = out[c].astype(bool)
    return out


def _matching_findings(cust: pd.DataFrame, cv: pd.DataFrame) -> list[Finding]:
    f: list[Finding] = []
    vc = cust[cust["vat_conflict"]]
    if len(vc):
        f.append(Finding(
            "MATCH_VAT_CONFLICT", SEV_WARNING, len(vc),
            [f"{r.code} {r.name if isinstance(r.name, str) else ''}: {r.vat} / {r.conflict_cv_vat} "
             f"({r.conflict_cv_name if isinstance(r.conflict_cv_name, str) else '?'})" for r in vc.head(10).itertuples()],
            {"codes": vc["code"].tolist(), "rematched_by_vat": int(vc["match_method"].eq("vat").sum()),
             "not_in_cerved": int((~vc["in_cerved"]).sum())}))
    vd = cust[cust["vat_differs"]]
    if len(vd):
        f.append(Finding("MATCH_VAT_DIFFERS", SEV_WARNING, len(vd),
                         [f"{r.code}: {r.vat} / {r.cv_vat}" for r in vd.head(10).itertuples()]))
    active = (cust["balance"] != 0) | (cust["turnover_12m"] > 0)
    used = set(cust.loc[active & cust["in_cerved"], "cv_row"].astype(int))
    unm = cv[~cv["cv_row"].isin(used)]
    if len(unm):
        f.append(Finding("CV_UNMATCHED", SEV_INFO, len(unm),
                         [f"{c or '-'} {n}" for c, n in unm[["code", "name"]].fillna("").values][:10],
                         {"rows": unm["cv_row"].astype(int).tolist()}))
    return f


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------
@dataclass
class LoadedData:
    """The three tidy tables (None if missing), customer base with Cerved match, findings."""
    checkfidi: pd.DataFrame | None = None
    cerved: pd.DataFrame | None = None
    ar: pd.DataFrame | None = None
    md105: pd.DataFrame | None = None                          # optional customer master (opening date)
    findings: list[Finding] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)      # kind -> file name
    rows_read: dict[str, int] = field(default_factory=dict)    # kind -> raw data rows
    customers: pd.DataFrame | None = None                      # checkfidi + Cerved match
    cache: dict[Any, Any] = field(default_factory=dict, repr=False)

    @property
    def missing(self) -> list[str]:
        return [k for k in KINDS if getattr(self, k if k != KIND_AR else "ar") is None]

    @property
    def ok(self) -> bool:
        """True if a simulation is possible (Check fidi present)."""
        return self.customers is not None

    @property
    def default_reference_date(self) -> pd.Timestamp | None:
        """Latest AR124 invoice date (None without AR124)."""
        if self.ar is None or self.ar["invoice_date"].notna().sum() == 0:
            return None
        return pd.Timestamp(self.ar["invoice_date"].max()).normalize()

    def matched_customers(self, reject_vat_conflict: bool = True) -> pd.DataFrame | None:
        """Customer base for a matching rule: the default one is ``customers``; the legacy rule
        (code match kept even when the VATs differ) is computed once and cached."""
        if reject_vat_conflict or self.checkfidi is None:
            return self.customers
        key = ("customers", "legacy_matching")
        if key not in self.cache:
            self.cache[key] = match_cerved(self.checkfidi, self.cerved, reject_vat_conflict=False)
        return self.cache[key]

    def findings_for(self, reject_vat_conflict: bool = True) -> list[Finding]:
        """Findings consistent with the matching rule actually used: ``findings`` holds the default
        rule (MATCH_VAT_CONFLICT); with the legacy rule the matching findings are recomputed
        (MATCH_VAT_DIFFERS, CV_UNMATCHED of that matching)."""
        if reject_vat_conflict or self.checkfidi is None or self.cerved is None:
            return self.findings
        key = ("findings", "legacy_matching")
        if key not in self.cache:
            base = [f for f in self.findings if not f.code.startswith(("MATCH_", "CV_UNMATCHED"))]
            self.cache[key] = base + _matching_findings(self.matched_customers(False), self.cerved)
        return self.cache[key]

    def finalize(self) -> "LoadedData":
        """(Re)build the matched customer base and the missing-file / matching findings."""
        self.findings = [f for f in self.findings
                         if not f.code.startswith(("MISSING_", "MATCH_", "CV_UNMATCHED"))]
        self.cache.clear()
        for kind in self.missing:
            self.findings.append(Finding(
                f"MISSING_{kind.upper()}", SEV_ERROR if kind == KIND_CHECKFIDI else SEV_WARNING, 1,
                [], {"unavailable": UNAVAILABLE_IF_MISSING[kind]}))
        if self.checkfidi is None:
            self.customers = None
            return self
        self.customers = match_cerved(self.checkfidi, self.cerved)
        if self.cerved is not None:
            self.findings.extend(_matching_findings(self.customers, self.cerved))
        return self


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _as_source(src: Any) -> tuple[str, bytes]:
    """Path / (name, bytes) / file-like with .name and .getvalue() or .read() -> (name, bytes)."""
    if isinstance(src, (str, Path)):
        p = Path(src)
        return p.name, p.read_bytes()
    if isinstance(src, tuple) and len(src) == 2:
        name, data = src
        return str(name), data if isinstance(data, bytes) else bytes(data)
    name = getattr(src, "name", "upload")
    if hasattr(src, "getvalue"):
        return str(name), src.getvalue()
    if hasattr(src, "read"):
        return str(name), src.read()
    raise TypeError(f"Unsupported source type: {type(src).__name__}")


def _engine(name: str, data: bytes) -> str:
    if data[:4] == b"\xd0\xcf\x11\xe0":
        return "xlrd"
    if data[:2] == b"PK":
        return "openpyxl"
    raise LoaderError(f"File '{name}' is not an Excel file (.xlsx or .xls).")


def read_file(name: str, data: bytes) -> tuple[str | None, pd.DataFrame | None, str | None]:
    """Find the sheet whose header matches a known signature. Returns (kind, raw df, sheet)."""
    engine = _engine(name, data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for header in HEADER_ROWS:
            heads = pd.read_excel(io.BytesIO(data), sheet_name=None, nrows=0, engine=engine, header=header)
            for sheet, h in heads.items():
                kind = detect_kind(h.columns)
                if kind is None:
                    continue
                # dtype=object: cells are kept as they are (numbers, dates, text). Without it pandas turns
                # a text column like "12.500" / "3.000" into the floats 12.5 / 3.0 before our parser sees
                # it; the cleaners read every value themselves (parse_numbers / parse_dates / code_to_str).
                raw = pd.read_excel(io.BytesIO(data), sheet_name=sheet, engine=engine, dtype=object, header=header)
                return kind, raw, sheet
    return None, None, None


def load_files(sources: Iterable[Any], strict: bool = False) -> LoadedData:
    """Load any number of files (paths, (name, bytes) pairs, or uploaded file objects).

    Each file is recognised by its columns. Unrecognised or invalid files become findings
    (or raise ``LoaderError`` when ``strict``). If two files of the same kind are given,
    the first one is kept.
    """
    ld = LoadedData()
    for src in sources:
        name, data = _as_source(src)
        try:
            kind, raw, _sheet = read_file(name, data)
            if kind is None:
                raise LoaderError(f"File '{name}' not recognised: none of its sheets has the "
                                  "columns of Check fidi, Cerved, AR124 or MD105.")
            if kind in ld.sources:
                ld.findings.append(Finding("FILE_DUPLICATE_KIND", SEV_WARNING, 1, [name],
                                           {"kind": kind, "kept": ld.sources[kind]}))
                continue
            df, fnd = CLEANERS[kind](raw, name)
        except LoaderError as e:
            if strict:
                raise
            ld.findings.append(Finding("FILE_INVALID", SEV_ERROR, 1, [name], {"message": str(e)}))
            continue
        except Exception as e:  # unreadable/corrupted workbook
            if strict:
                raise LoaderError(f"File '{name}' cannot be read: {e}") from e
            ld.findings.append(Finding("FILE_INVALID", SEV_ERROR, 1, [name],
                                       {"message": f"File '{name}' cannot be read: {e}"}))
            continue
        setattr(ld, "ar" if kind == KIND_AR else kind, df)
        ld.sources[kind] = name
        ld.rows_read[kind] = len(raw)
        for f in fnd:
            f.details.setdefault("file", name)
        ld.findings.extend(fnd)
    return ld.finalize()


def load_folder(folder: str | Path, strict: bool = False) -> LoadedData:
    """Load every .xls/.xlsx in a folder (default data/ next to the app)."""
    p = Path(folder)
    files = sorted(x for x in p.glob("*") if x.suffix.lower() in (".xls", ".xlsx")
                   and not x.name.startswith("~$"))
    return load_files(files, strict=strict)
