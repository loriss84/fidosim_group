# Simulatore Fido SIAD Romania (v3.2)

Credit limit simulator for SIAD Romania (company 42): formula v3.2, comparison with today's JDE limits,
parameter lab, Customer page with the public balance sheet from ANAF (second opinion, not in the formula).

- Start: `run.bat` (Windows) or `run.sh`, then load the 4 input files (Check fidi, Cerved, AR124, MD105 optional).
- Full guide in Italian: [LEGGIMI.md](LEGGIMI.md). Specification: [SPEC.md](SPEC.md), UX: [UX.md](UX.md).
- Tests: `python -m tests.run_all` (needs the real input files in `data/`).

The `data/` folder is kept out of git on purpose: the input files contain customer data.
