"""Country profiles: currency, VAT prefix, local defaults and the public balance-sheet source.

The simulator works on one country at a time (one JD Edwards company). The active country is the
``country`` parameter; the UI calls ``set_active(params.country)`` at every run, the tests and the
core functions that need it (loaders, texts) read ``active()``.

Amounts are always in the country's currency (the "local currency"). Internal column names that
still say ``_ron`` (``cerved_limit_ron``) hold local-currency amounts: kept to avoid touching the
Romanian engine, which must give exactly the same numbers as the single-country simulator.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Country:
    code: str                    # ISO 3166 alpha-2
    name_it: str
    name_en: str
    currency: str                # ISO 4217, the currency of the JDE company and of Check fidi / AR124
    vat_prefix: str              # VAT prefix stripped by the Cerved matching ("RO 14697790" -> "14697790")
    eur_rate: float              # local currency per 1 EUR (default; a parameter in the simulator)
    min_limit: int               # minimum limit for limits > 0
    rounding_step: int           # limits rounded to this
    approval_min_change: int     # materiality of a change that needs approval
    step_factor: float           # UI step of local-currency parameters = Romanian step x this
    balance_source: str          # "anaf" | "ruz" | "manual" (see core.bs_providers)
    balance_round_to: int        # balance-sheet capacity rounded down to this
    register_name: str           # name of the public register shown in the UI
    register_url: str            # search page of the register ({key} = local tax id when known)
    tax_id_label_it: str
    tax_id_label_en: str
    company_words: tuple[str, ...]   # words in the Check fidi "Company" column that identify the country
    intercompany: tuple[str, ...] = ()
    notes_it: str = ""
    notes_en: str = ""
    company_codes: tuple[int, ...] = field(default=())

    def rounding_choices(self) -> list[int]:
        """Rounding steps offered in the Lab (RON: 100, 500, 1.000, 5.000)."""
        base = {"RON": (100, 500, 1000, 5000), "EUR": (50, 100, 250, 1000),
                "CZK": (1000, 5000, 10000, 25000), "HUF": (10000, 50000, 100000, 500000)}
        return list(base.get(self.currency, (100, 500, 1000, 5000)))

    def name(self, lang: str = "it") -> str:
        return self.name_it if lang == "it" else self.name_en

    def tax_id_label(self, lang: str = "it") -> str:
        return self.tax_id_label_it if lang == "it" else self.tax_id_label_en

    def param_defaults(self) -> dict[str, Any]:
        """Parameters that depend on the country (everything else is the group formula)."""
        return {"country": self.code, "eur_rate": self.eur_rate, "min_limit": self.min_limit,
                "rounding_step": self.rounding_step, "approval_min_change": self.approval_min_change,
                "intercompany_codes": list(self.intercompany)}


RO_INTERCOMPANY = ("30001069", "30005389", "30001070")   # SIAD Bulgaria, SIAD Macchine Impianti, SIAD SpA

PROFILES: dict[str, Country] = {c.code: c for c in [
    Country("RO", "Romania", "Romania", "RON", "RO", 4.975, 5000, 1000, 5000, 1.0, "anaf", 1000,
            "ANAF", "https://webservicesp.anaf.ro/bilant?an={year}&cui={key}",
            "codice fiscale (CUI)", "tax code (CUI)", ("ROMANIA",), RO_INTERCOMPANY,
            company_codes=(42,)),
    Country("SK", "Slovacchia", "Slovakia", "EUR", "SK", 1.0, 1000, 250, 1000, 0.25, "ruz", 250,
            "RÚZ (Register účtovných závierok)",
            "https://www.registeruz.sk/cruz-public/domain/accountingentity/simplesearch",
            "IČO / DIČ", "IČO / DIČ", ("SLOVAK", "SLOVENSK")),
    Country("AT", "Austria", "Austria", "EUR", "AT", 1.0, 1000, 250, 1000, 0.25, "manual", 250,
            "Firmenbuch (JustizOnline)", "https://justizonline.gv.at/jop/web/firmenbuchabfrage",
            "numero Firmenbuch / UID", "company register no. / UID", ("AUSTRIA", "ÖSTERREICH", "OSTERREICH"),
            notes_it="Lettura automatica possibile con la chiave HVD del Firmenbuch (non ancora collegata).",
            notes_en="Automatic reading possible with the Firmenbuch HVD key (not connected yet)."),
    Country("CZ", "Repubblica Ceca", "Czech Republic", "CZK", "CZ", 25.3, 25000, 5000, 25000, 5.0, "manual", 5000,
            "Sbírka listin (justice.cz)", "https://or.justice.cz/ias/ui/rejstrik-$firma?ico={key}",
            "IČO", "IČO", ("CZECH", "CESK", "ČESK")),
    Country("DE", "Germania", "Germany", "EUR", "DE", 1.0, 1000, 250, 1000, 0.25, "manual", 250,
            "Unternehmensregister", "https://www.unternehmensregister.de/de/suche",
            "USt-IdNr.", "VAT no. (USt-IdNr.)", ("GERMAN", "DEUTSCHLAND")),
    Country("HU", "Ungheria", "Hungary", "HUF", "HU", 400.0, 400000, 100000, 400000, 80.0, "manual", 100000,
            "e-beszámoló", "https://e-beszamolo.im.gov.hu/oldal/beszamolo_kereses",
            "adószám (prime 8 cifre)", "tax number (first 8 digits)", ("HUNGARY", "MAGYAR")),
]}
DEFAULT = "RO"
CODES = list(PROFILES)

_active = [DEFAULT]


def get(code: str | None) -> Country:
    return PROFILES.get(str(code or DEFAULT).upper(), PROFILES[DEFAULT])


def set_active(code: str | None) -> Country:
    """Make ``code`` the active country (unknown codes fall back to Romania)."""
    c = get(code)
    _active[0] = c.code
    return c


def active() -> Country:
    return PROFILES[_active[0]]


def currency() -> str:
    return active().currency


_RON = re.compile(r"\bRON\b")


def localise(text: str) -> str:
    """Texts are written in RON (the first country): use the active currency instead."""
    cur = active().currency
    if cur == "RON" or "RON" not in text:
        return text
    return _RON.sub(cur, text)


def strip_vat_prefix(s: str) -> str:
    """Remove the active country's VAT prefix from a normalised VAT key (letters and digits)."""
    p = active().vat_prefix
    return s[len(p):] if p and s.startswith(p) else s


def detect(checkfidi: pd.DataFrame | None) -> str | None:
    """Country of a Check fidi extract: company name first, then known company codes, then the VAT
    prefixes of the customers (most frequent EU prefix). None if nothing says it."""
    if checkfidi is None or checkfidi.empty:
        return None
    if "company" in checkfidi:
        names = " ".join(str(x).upper() for x in checkfidi["company"].dropna().unique()[:5])
        for c in PROFILES.values():
            if any(w in names for w in c.company_words):
                return c.code
    if "company_code" in checkfidi:
        codes = pd.to_numeric(checkfidi["company_code"], errors="coerce").dropna().astype(int).unique()
        for c in PROFILES.values():
            if any(int(x) in c.company_codes for x in codes):
                return c.code
    if "vat" in checkfidi:
        pref = (checkfidi["vat"].dropna().astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
                .str.extract(r"^([A-Z]{2})")[0].dropna())
        known = pref[pref.isin(list(PROFILES))]
        if len(known) and known.value_counts().iloc[0] >= 0.3 * len(pref):
            return str(known.value_counts().index[0])
    return None
