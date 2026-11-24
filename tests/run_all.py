"""Run all tests without pytest: ``cd fido_v3 && python -m tests.run_all``."""
from __future__ import annotations

import importlib
import pkgutil
import sys
import time
import traceback
import warnings
from pathlib import Path


def main() -> int:
    warnings.filterwarnings("ignore")
    here = Path(__file__).parent
    mods = sorted(m.name for m in pkgutil.iter_modules([str(here)]) if m.name.startswith("test_"))
    ok = fail = 0
    for name in mods:
        mod = importlib.import_module(f"tests.{name}")
        for fn_name in sorted(n for n in dir(mod) if n.startswith("test_")):
            fn = getattr(mod, fn_name)
            if not callable(fn):
                continue
            t = time.time()
            try:
                fn()
                ok += 1
                print(f"ok    {name}.{fn_name}  ({time.time() - t:.2f}s)")
            except Exception:
                fail += 1
                print(f"FAIL  {name}.{fn_name}")
                traceback.print_exc()
    print(f"\n{ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
