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
