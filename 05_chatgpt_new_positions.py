"""
Backward-compatibility stub: new positions ChatGPT is now pipeline step 07.
Run 07_chatgpt_new_positions.py directly, or this script (delegates to 07).
"""
import importlib.util
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "07_chatgpt_new_positions.py"
    spec = importlib.util.spec_from_file_location("step07", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["step07"] = mod
    spec.loader.exec_module(mod)
    mod.main()
