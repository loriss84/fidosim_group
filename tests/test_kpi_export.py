"""KPIs, scenario comparison, changed customers, sensitivity, Excel export."""
import io

import pandas as pd

from core.engine import simulate
from core.export import to_excel
from core.kpi import KPI_KEYS, changed_customers, compare, kpis
from core.params import Params, OLD_V3
from core.sensitivity import sensitivity, value_range
from tests.helpers import REF, cf_row, cv_row, make_data

P = Params(reference_date=REF, **OLD_V3)  # unit tests of the v3 mechanics (v3.1: see test_behaviour)
CF = [cf_row(code="1", t12=120000, balance=30000, limit=30000, ordered=100),
      cf_row(code="2", t12=1200000, balance=100000, limit=50000),
      cf_row(code="3", t12=0, balance=10, risk="S09")]
CV = [cv_row(code=1.0), cv_row(code=2.0, score="CAUTELA", fido=120000, fatt=1000000)]


def test_kpis_and_compare():
    d = make_data(CF, CV)
    k = kpis(simulate(d, P))
    assert list(k) == KPI_KEYS
    assert k["n_active"] == 3 and k["n_scope"] == 2
    assert k["over_new_n"] == 1 and k["excess_new"] == 8100         # 30.100 vs 22.000
    assert k["orders_over_new_n"] == 1 and k["over_current_n"] == 2  # 100.000 > 50.000, 30.100 > 30.000
    assert k["higher_n"] == 1 and k["lower_n"] == 1
    assert k["plausibility_n"] == 1 and k["n_caution"] == 1
    k2 = kpis(simulate(d, P.replace(multiplier=3)))
    c = compare(k, k2).set_index("key")
    assert c.loc["limits_proposed_active", "delta"] == k2["limits_proposed_active"] - k["limits_proposed_active"]
    ch = changed_customers(simulate(d, P), simulate(d, P.replace(multiplier=3)))
    assert set(ch.code) == {"1"} and ch.loc[0, "change"] == "BOTH"   # 2 stays capped at 120.000


def test_sensitivity_and_export():
    d = make_data(CF, CV)
    s = sensitivity(d, P, "multiplier", [1, 2, 3])
    assert list(s["value"]) == [1, 2, 3] and s["limits_proposed_active"].is_monotonic_increasing
    assert value_range("multiplier", 1, 3, 5) == [1.0, 1.5, 2.0, 2.5, 3.0]
    assert value_range("min_days", 0, 30, 4) == [0, 10, 20, 30]
    for lang in ("it", "en"):
        b = to_excel(simulate(d, P), P, lang)
        x = pd.read_excel(io.BytesIO(b), sheet_name=None)
        assert len(x) == 3
        cust = list(x.values())[0]
        assert len(cust) == 3 and ("Fido proposto" if lang == "it" else "Proposed limit") in cust.columns
