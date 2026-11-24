"""Synthetic data builders using the real source headers (so loaders are exercised too)."""
from __future__ import annotations

import pandas as pd

from core.loaders import LoadedData, clean_ar, clean_cerved, clean_checkfidi

CF_DEFAULT = {"Code": "1", "Name": "X", "Company Code": 42, "Company": "SIAD Romania SRL",
              "Balance": 0.0, "Current": 0.0, "Overdue": 0.0, "Ordered": 0.0, "Delivered": 0.0,
              "Credit Limit": 0.0, "% Fill": 0.0, "Code  Risk Class (AMF)": "E00",
              "Code  Cod. DORIS": "CBT", "Block Description": None, "Turnover 12 months": 0.0,
              "Turnover": 0.0, "VAT": None}
CV_DEFAULT = {"RIFERIMENTO": None, "PARTITA_IVA": None, "RAGIONE_SOCIALE": "X SRL",
              "SCORE SEMAFORICO": "AFFIDABILE", "VALORE_FIDO": None, "VALUTA": "RON",
              "CLASSE_AFFIDABILITA": 3.0, "FATTURATO_NO_BIL": None, "ABITUDINI_PAGAMENTO": 21}
AR_DEFAULT = {"Customer\nNumber": 1, "Document\nNumber": 1.0, "Name\nAlpha": "X",
              "Individual\nTax\nID": None, "Tax ID": None, "Address\nLine 2": None,
              "Postal Code": None, "City": None, "State": None, "Invoice Date": None,
              "Due Date": None, "Gross\nAmount": 0.0, "Date Invoice Closed": None}
REF = "2026-11-20"


def cf_row(**kw) -> dict:
    keymap = {"code": "Code", "name": "Name", "balance": "Balance", "overdue": "Overdue",
              "ordered": "Ordered", "delivered": "Delivered", "limit": "Credit Limit",
              "risk": "Code  Risk Class (AMF)", "t12": "Turnover 12 months", "vat": "VAT"}
    r = dict(CF_DEFAULT)
    r.update({keymap.get(k, k): v for k, v in kw.items()})
    return r


def cv_row(**kw) -> dict:
    keymap = {"code": "RIFERIMENTO", "vat": "PARTITA_IVA", "name": "RAGIONE_SOCIALE",
              "score": "SCORE SEMAFORICO", "fido": "VALORE_FIDO", "cur": "VALUTA",
              "fatt": "FATTURATO_NO_BIL"}
    r = dict(CV_DEFAULT)
    r.update({keymap.get(k, k): v for k, v in kw.items()})
    return r


def ar_row(cust, inv, due, amount, closed=None) -> dict:
    r = dict(AR_DEFAULT)
    r.update({"Customer\nNumber": cust, "Invoice Date": pd.Timestamp(inv),
              "Due Date": pd.Timestamp(due) if due else pd.NaT, "Gross\nAmount": amount,
              "Date Invoice Closed": pd.Timestamp(closed) if closed else pd.NaT})
    return r


def make_data(cf: list[dict], cv: list[dict] | None = None, ar: list[dict] | None = None) -> LoadedData:
    ld = LoadedData()
    ld.checkfidi, f1 = clean_checkfidi(pd.DataFrame(cf))
    ld.findings += f1
    if cv is not None:
        ld.cerved, f2 = clean_cerved(pd.DataFrame(cv, columns=list(CV_DEFAULT)))
        ld.findings += f2
    if ar is not None:
        ld.ar, f3 = clean_ar(pd.DataFrame(ar, columns=list(AR_DEFAULT)))
        ld.findings += f3
    return ld.finalize()


def one(result: pd.DataFrame, code: str) -> pd.Series:
    m = result[result["code"] == code]
    assert len(m) == 1, f"customer {code} not found once in result"
    return m.iloc[0]


def close(a, b, tol=1e-6) -> None:
    assert abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b))), f"{a} != {b}"
