"""CodeCoach-RSI web app. Run:  python -m streamlit run app/streamlit_app.py

Read-only over archive/ and results/ (the live pages write only to archive/live/). Each page is a small module in
app/views/, imported only when selected, so the first screen loads fast (torch is not imported until needed).
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from common import get_archive  # noqa: E402

PAGES = {
    "1. Overview": "overview",
    "2. Evolution timeline": "evolution",
    "3. Version vs previous version": "compare",
    "4. Improver evolution (recursive step)": "improver",
    "5. Self-training & verifier": "selftrain",
    "6. Distillation (live)": "distill",
    "7. Try it (live learning)": "tryit",
    "8. Live run": "live",
    "9. Safety & limitations": "safety_page",
}

st.set_page_config(page_title="CodeCoach-RSI", page_icon="🧭", layout="wide")
page = st.sidebar.radio("Page", list(PAGES), key="page")
st.sidebar.caption("Bounded, sandboxed recursive self-improvement: the system edits only whitelisted files, under a fixed "
                   "external evaluator, with rollback.")
module = importlib.import_module(f"views.{PAGES[page]}")
module.render(get_archive())
