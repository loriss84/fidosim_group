# Simulatore Fido SIAD (multi-paese, v4.0)

Credit limit simulator for the SIAD group companies: formula v3.2, comparison with today's JDE limits,
parameter lab, Customer page with the public balance sheet as a second opinion (not in the formula).

- Countries: Romania (RON, ANAF), **Slovakia (EUR, RÚZ open API)**, Austria, Czech Republic, Germany, Hungary
  (local currency and defaults; balance sheet typed in from the register). One country at a time, chosen on the
  Data page or recognised from the Check fidi file. Cerved is optional (without it every customer is "not in Cerved").
- Romania gives exactly the same results as `fidosim_romania` (commit 30d71e7): `tests/test_country.py::test_golden_romania_unchanged`.
- Start: `run.bat` (Windows) or `run.sh`, then load Check fidi, AR124, MD105 (optional) and Cerved (optional).
- Full guide in Italian: [LEGGIMI.md](LEGGIMI.md). Specification: [SPEC.md](SPEC.md), UX: [UX.md](UX.md).
- Tests: `python -m tests.run_all`. The page tests with real numbers need the real Romanian files in `data/`;
  everything else runs on synthetic data (`python -m tests.synthetic <folder> RO|SK`).

The `data/` folder is kept out of git on purpose: the input files contain customer data.
