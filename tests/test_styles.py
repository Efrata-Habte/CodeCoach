"""Style rewrites must never change behaviour."""
from codecoach.problems import PROBLEMS
from codecoach.sandbox import run_tests_many
from codecoach.styles import style_variants


def test_every_style_variant_still_passes_the_tests() -> None:
    for p in PROBLEMS:
        variants = style_variants(p.source)
        results = run_tests_many(variants, p.func_name, p.tests)
        assert all(r.passed for r in results), f"{p.name}: a rewrite changed behaviour"


def test_first_variant_is_the_original_and_rewrites_add_variety() -> None:
    counts = [len(style_variants(p.source)) for p in PROBLEMS]
    assert all(c >= 1 for c in counts)
    assert sum(c > 1 for c in counts) >= 10  # most problems get extra styles
    p = PROBLEMS[0]  # sum_list uses `total += xs[i]`
    assert "total = total + xs[i]" in "\n".join(style_variants(p.source))
