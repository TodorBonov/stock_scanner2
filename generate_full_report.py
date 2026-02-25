"""
Backward-compatibility stub: Minervini report is now pipeline step 04.
Run 04_generate_full_report.py directly, or this script (delegates to 04).
"""
import importlib.util
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "04_generate_full_report.py"
    spec = importlib.util.spec_from_file_location("step04", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["step04"] = mod
    spec.loader.exec_module(mod)
    mod.main()
