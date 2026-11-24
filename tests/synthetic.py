"""Deterministic synthetic input files (Check fidi, Cerved, AR124, MD105) with the real headers.

The real files contain customer data and stay out of git. These files exercise the same code paths
(every reason, ceiling, currency, age band, behaviour band...) so that:

- ``tests/test_golden.py`` can check that the Romanian results are identical, customer by customer,
  to the ones of the single-country simulator (fidosim_romania, commit 30d71e7);
- the page tests can run on any PC without the real files;
- a country without Cerved (Slovakia) can be tried end to end.

Run ``python -m tests.synthetic <folder> [RO|SK]`` to write the four files into a folder.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REF = pd.Timestamp("2026-11-20")

COUNTRY = {
    # code: (company code, company name, VAT prefix, currency, amount scale vs RON)
    "RO": (42, "SIAD ROMANIA SRL", "RO", "RON", 1.0),
    "SK": (55, "SIAD SLOVAKIA spol. s r.o.", "SK", "EUR", 0.2),
}
INTERCOMPANY_RO = ["30001069", "30005389", "30001070"]
SPECIAL = ["S09", "EV9", "EV8", "EK9", "ES1"]
EXEMPT = ["EKM", "EPS", "EPU"]


def _vat(prefix: str, rng: np.random.Generator, i: int) -> str:
    if prefix == "SK":
        return f"SK20{rng.integers(10_000_000, 99_999_999)}"      # IČ DPH: SK + 10 digits
    return f"RO{10_000_000 + i * 7919 % 9_000_000}"


def build(country: str = "RO", n: int = 420, seed: int = 7) -> dict[str, pd.DataFrame]:
    """DataFrames keyed by kind, with the source headers."""
    comp, comp_name, prefix, cur, scale = COUNTRY[country]
    rng = np.random.default_rng(seed)
    codes = [str(30000100 + i * 13) for i in range(n)]
    if country == "RO":
        codes[:3] = INTERCOMPANY_RO
    cf, cv, ar, md = [], [], [], []
    doc = 1000
    for i, code in enumerate(codes):
        kind = rng.random()
        t12 = float(np.round(rng.lognormal(10.5, 1.4) * scale, 2)) if kind > 0.06 else 0.0
        if i % 37 == 5:
            t12 = -float(np.round(rng.uniform(100, 3000) * scale, 2))     # negative turnover (credit notes)
        terms = int(rng.choice([15, 30, 30, 30, 45, 60, 90]))
        delay = float(rng.choice([-5, 0, 0, 2, 4, 8, 15, 25, 40, 70]))
        risk = "E00"
        if i % 29 == 3:
            risk = SPECIAL[i % len(SPECIAL)]
        elif i % 31 == 4:
            risk = EXEMPT[i % len(EXEMPT)]
        vat = _vat(prefix, rng, i) if i % 23 != 7 else None
        if i % 41 == 9:
            vat = f"BG{rng.integers(100_000_000, 999_999_999)}"           # foreign customer
        overdue = float(np.round(t12 / 12 * rng.choice([0, 0, 0.2, 0.8, 2.0]), 2)) if t12 > 0 else 0.0
        balance = float(np.round(max(t12, 0) / 12 * terms / 30 * rng.uniform(0.3, 1.6), 2)) + overdue
        if t12 == 0 and i % 3 == 0:
            balance = float(np.round(rng.uniform(-500, 2500) * scale, 2))
        ordered = float(np.round(max(t12, 0) / 12 * rng.choice([0, 0, 0.1, 0.5]), 2))
        delivered = float(np.round(max(t12, 0) / 12 * rng.choice([0, 0, 0.05, 0.3]), 2))
        limit = float(np.round(max(t12, 0) / 12 * rng.choice([0, 1, 2, 3, 5]) / 1000) * 1000 * 1.0)
        cf.append({"Code": code, "Name": f"CLIENT {i:03d} SRL", "Company Code": comp, "Company": comp_name,
                   "Balance": balance, "Current": balance - overdue, "Overdue": overdue,
                   "Ordered": ordered, "Delivered": delivered, "Credit Limit": limit,
                   "% Fill": None, "Code  Risk Class (AMF)": risk, "Code  Cod. DORIS": "CBT",
                   "Block Description": None, "Turnover 12 months": t12, "Turnover": t12 * 1.3, "VAT": vat})
        # --- Cerved (Romania only) ---
        if country == "RO" and rng.random() < 0.72:
            score = rng.choice(["AFFIDABILE", "AFFIDABILE", "CAUTELA", "MASSIMA CAUTELA"])
            fido = float(np.round(max(t12, 1000) * rng.choice([0.0, 0.01, 0.02, 0.05, 0.2]) + rng.uniform(0, 1), 2))
            valuta = "RON"
            if i % 53 == 11:
                valuta, fido = "EUR", float(np.round(fido / 4.975, 2))
            elif i % 47 == 2:
                valuta = None
            elif i % 89 == 13:
                valuta = "USD"
            cvat = vat
            if i % 61 == 17 and vat:
                cvat = f"RO{rng.integers(1_000_000, 9_999_999)}"                  # VAT conflict
            cv.append({"RIFERIMENTO": float(code), "PARTITA_IVA": (cvat.replace("RO", "RO ") if cvat else None),
                       "RAGIONE_SOCIALE": f"CLIENT {i:03d} SRL", "SCORE SEMAFORICO": score,
                       "VALORE_FIDO": fido if i % 43 != 8 else None, "VALUTA": valuta,
                       "CLASSE_AFFIDABILITA": float(rng.integers(1, 10)),
                       "FATTURATO_NO_BIL": float(np.round(max(t12, 1) * rng.choice([3, 10, 40, 200]), 0)),
                       "ABITUDINI_PAGAMENTO": int(rng.integers(5, 90))})
            if i % 67 == 21:                                                       # duplicate code
                cv.append(dict(cv[-1], **{"PARTITA_IVA": None, "SCORE SEMAFORICO": "CAUTELA"}))
        # --- AR124 invoices: 14 months back from REF ---
        age_m = int(rng.choice([1, 2, 4, 7, 11, 14, 40, 120]))
        opened = REF - pd.DateOffset(months=age_m) - pd.Timedelta(days=int(rng.integers(0, 25)))
        n_months = min(age_m, 14)
        per_month = max(t12, 0) / max(min(n_months, 12), 1)
        for m in range(n_months):
            if rng.random() < 0.15:
                continue                                                           # month without purchases
            inv = REF - pd.DateOffset(months=m) - pd.Timedelta(days=int(rng.integers(0, 27)))
            for _k in range(int(rng.integers(1, 3))):
                amt = float(np.round(per_month / 1.5 * rng.uniform(0.5, 1.5), 2))
                if amt <= 0:
                    continue
                due = inv + pd.Timedelta(days=terms)
                closed = inv + pd.Timedelta(days=max(1, int(terms + delay + rng.normal(0, 4))))
                if closed > REF + pd.Timedelta(days=10) or rng.random() < 0.04:
                    closed = None
                doc += 1
                ar.append({"Customer\nNumber": int(code), "Document\nNumber": float(doc), "Name\nAlpha": f"CLIENT {i:03d}",
                           "Individual\nTax\nID": None, "Tax ID": vat, "Address\nLine 2": None,
                           "Postal Code": None, "City": None, "State": None, "Invoice Date": inv,
                           "Due Date": due, "Gross\nAmount": amt, "Date Invoice Closed": closed})
            if rng.random() < 0.08:                                                # credit note
                doc += 1
                ar.append({"Customer\nNumber": int(code), "Document\nNumber": float(doc), "Name\nAlpha": f"CLIENT {i:03d}",
                           "Individual\nTax\nID": None, "Tax ID": vat, "Address\nLine 2": None,
                           "Postal Code": None, "City": None, "State": None, "Invoice Date": inv,
                           "Due Date": inv, "Gross\nAmount": -float(np.round(per_month * 0.1, 2)),
                           "Date Invoice Closed": inv})
        if i % 19 != 6:
            md.append({"Cliente": int(code), "Descrizione Cliente": f"CLIENT {i:03d} SRL", "Stato Cliente": "A",
                       "Tax ID": vat, "Payment Terms - A/R": f"E{terms:02d}",
                       "Date - Account Opened": max(opened, pd.Timestamp("2006-08-31")) if i % 11 else
                       pd.Timestamp("2006-08-31")})
    out = {"checkfidi": pd.DataFrame(cf), "ar124": pd.DataFrame(ar), "md105": pd.DataFrame(md)}
    if cv:
        out["cerved"] = pd.DataFrame(cv)
    return out


def _xlsx(df: pd.DataFrame, sheet: str, title: str | None = None) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=sheet, index=False, startrow=1 if title else 0)
        if title:
            w.sheets[sheet].cell(row=1, column=1, value=title)
    return bio.getvalue()


def files(country: str = "RO", **kw) -> list[tuple[str, bytes]]:
    """[(file name, xlsx bytes)] ready for ``loaders.load_files``."""
    d = build(country, **kw)
    cc = country.lower()
    out = [(f"check_fidi_{cc}.xlsx", _xlsx(d["checkfidi"], "Result")),
           (f"ar124_{cc}.xlsx", _xlsx(d["ar124"], "AR124")),
           (f"md105_{cc}.xlsx", _xlsx(d["md105"], "MD105.Customer Master", "MD105 Customer Master"))]
    if "cerved" in d:
        out.append((f"cerved_{cc}.xlsx", _xlsx(d["cerved"], "Slim Report")))
    return out


def write(folder: str | Path, country: str = "RO", **kw) -> list[Path]:
    p = Path(folder)
    p.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, b in files(country, **kw):
        (p / name).write_bytes(b)
        paths.append(p / name)
    return paths


if __name__ == "__main__":
    for f in write(sys.argv[1] if len(sys.argv) > 1 else "data_synthetic",
                   sys.argv[2].upper() if len(sys.argv) > 2 else "RO"):
        print(f)
