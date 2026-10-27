"""Page 9: safety guard-rails (mapped to code) and the honest limitations list."""
import streamlit as st
from common import has_results

LIMITATIONS = [
    "**Bounded, not open-ended.** The system edits two whitelisted files through a fixed menu of AST operators (constrained program search). "
    "Unrestricted recursive self-improvement has not been demonstrated; this is not it.",
    "**Tests define correctness.** A wrong fix that passes our tests would be accepted; the tests were written by us.",
    "**Small, synthetic data.** 24 functions, single-place bugs, 5 classes. The classifier may learn template artifacts; the hand-written "
    "final test (different style) is the honest check.",
    "**Dev-set overfitting.** Many generations select on a small dev set. meta_dev, the 3-seed test numbers and the final test are the "
    "numbers to trust.",
    "**Noise.** With 6-20 samples per class one mistake moves a class F1 by about 0.1; differences below ~0.05 macro-F1 are not resolvable.",
    "**Level 2 has a weak signal.** Few edits pass the dev gate, so utilities often tie at 0; a null result is the likely outcome.",
    "**Single machine.** Latency is one CPU, one thread; results are reproducible on one machine, not guaranteed bit-identical elsewhere.",
    "**Sandbox is not a security jail.** Static check + subprocess + timeout/memory cap + hash checks contain a buggy search; a determined "
    "attacker would need an OS-level sandbox. The Linux/macOS memory cap is untested.",
]


def render(a) -> None:
    from codecoach import safety
    st.header("Safety and limitations")
    st.markdown("""| Guard-rail | What it stops | Code |
|---|---|---|
| Edit whitelist | the system overwriting the library, config or baseline: it may only write under `archive/` | `safety.assert_write_allowed` |
| Static check | forbidden imports/names (`os`, `open`, `exec`, `eval`, ...), dunder escapes, code at import time, wrong interface | `safety.check` |
| Tamper detection | any change to `codecoach/`, `data/`, `tests/`, `scripts/`, `evolvable/`, `config.py` during an evaluation: the run aborts | `safety.protected_hashes`, `assert_unchanged` |
| Isolated execution | infinite loops, runaway memory, crashes: child process with timeout and memory cap | `safety.run_isolated` |
| Budget caps | endless search: `generations`, `patience`, `max_rounds`, bounded constants | `config.py`, `code_editor` bounds |""")
    c1, c2 = st.columns(2)
    c1.markdown("**Allowed imports (pipeline):** " + ", ".join(f"`{m}`" for m in sorted(safety.ALLOWED_IMPORTS["pipeline"])) + ", `codecoach.feature_blocks`")
    c2.markdown("**Forbidden names:** " + ", ".join(f"`{n}`" for n in sorted(safety.FORBIDDEN_NAMES)[:24]) + ", ...")
    st.subheader("Tamper check, live")
    if "baseline_hashes" not in st.session_state:
        st.session_state.baseline_hashes = safety.protected_hashes()
    st.write(f"{len(st.session_state.baseline_hashes)} protected files were hashed when this session started.")
    if st.button("Re-hash now and compare"):
        try:
            safety.assert_unchanged(st.session_state.baseline_hashes)
            st.success("All protected files are unchanged since this session started.")
        except safety.TamperError as err:
            st.error(str(err))
    st.subheader("Limitations")
    for item in LIMITATIONS:
        st.markdown(f"- {item}")
