"""
Backward-compatibility stub: existing positions ChatGPT is now pipeline step 06.
Run 06_chatgpt_existing_positions.py directly, or this script (delegates to 06).
"""
import importlib.util
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "06_chatgpt_existing_positions.py"
    spec = importlib.util.spec_from_file_location("step06", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["step06"] = mod
    spec.loader.exec_module(mod)
    mod.main()
