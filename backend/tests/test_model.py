"""Model helpers that need no Vertex call."""


def test_search_suggestion_from_grounding() -> None:
    from types import SimpleNamespace as Ns

    from app.model import SUGGESTION_MAX, search_suggestion_from

    def resp(html: object) -> object:
        sep = Ns(rendered_content=html)
        return Ns(candidates=[Ns(grounding_metadata=Ns(search_entry_point=sep))])

    assert search_suggestion_from(resp("<a>x</a>")) == "<a>x</a>"
    assert search_suggestion_from(resp(None)) == ""
    assert search_suggestion_from(resp("x" * (SUGGESTION_MAX + 1))) == ""  # dropped, not cut
    assert search_suggestion_from(Ns(candidates=[])) == ""
    assert search_suggestion_from(Ns(candidates=[Ns(grounding_metadata=None)])) == ""


def test_predict_prompt_keeps_the_speakers_language() -> None:
    # Live check 16 Oct: an English Trump brief came back 1/3 Hindi, 1/3 Hinglish, which
    # can never match English speech. The prompt must tie language to the speaker.
    from app.model import PREDICT_PROMPT

    p = PREDICT_PROMPT.format(topic="t", speaker="s", n=12)
    assert "language THIS speaker actually speaks" in p
    assert "gets every claim in en" in p
    assert "Never translate" in p
