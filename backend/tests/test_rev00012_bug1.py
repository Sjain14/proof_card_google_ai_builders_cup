"""Bug 1 of the rev00012 prod verify (16 Oct 2026): true claims came back UNVERIFIABLE."""

from app.proof import match_passage, tokens
from app.schemas import Verdict, gate_verdict

TRUE_CLAIM = "US inflation hit 9.1 percent in June 2022, the highest in 40 years"


# ---------- bug 1: true claims came back UNVERIFIABLE ----------


def test_paraphrased_source_backs_a_true_claim() -> None:
    p = "Inflation peaked at 9.1% in June 2022, a four-decade high."
    s = match_passage(TRUE_CLAIM, p).score
    assert s >= 0.6
    assert gate_verdict(Verdict.TRUE, s) is Verdict.TRUE


def test_percent_sign_and_number_words_normalise() -> None:
    assert tokens("9.1%") == tokens("9.1 percent") == tokens("9.1 per cent")
    assert "40" in tokens("a four-decade high")
    assert "years" in tokens("a four-decade high")
    assert tokens("the largest rise") == tokens("the highest rise")
    # "one" stays a word: "one of the largest" must not demand a "1" in the source.
    assert "1" not in tokens("one of the largest economies")


def test_a_wrong_number_still_caps_support() -> None:
    p = "Inflation peaked at 7.2 percent in June 2022, a four-decade high."
    m = match_passage(TRUE_CLAIM, p)
    assert m.score <= 0.5
    assert m.conflict
    assert gate_verdict(Verdict.TRUE, m.score) is Verdict.UNVERIFIABLE
