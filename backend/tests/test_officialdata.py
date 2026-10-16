"""Official statistics source (World Bank API) for country figure claims.

Prod 16 Oct 2026: "India per capita GDP is higher than Japan" ended FAILED on 4 of 4 live
runs; its grounding sources were JS data portals with no figures in the HTML."""

import json

import httpx

from app.model import Assessment, Evidence
from app.officialdata import countries_of, metric_of, official_evidence, render
from app.pipeline import Deps, build_card
from app.proof import HttpFetcher, InMemorySnapshots
from app.schemas import Verdict
from app.store import InMemoryStore


def _rows(indicator: str, label: str, vals: dict[str, float]) -> bytes:
    rows = [
        {
            "indicator": {"id": indicator, "value": label},
            "country": {"id": k[:2], "value": k},
            "date": "2025",
            "value": v,
        }
        for k, v in vals.items()
    ]
    return json.dumps([{"page": 1}, rows]).encode()


def _transport(wb_body: bytes) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.url.host == "api.worldbank.org":
            return httpx.Response(
                200, content=wb_body, headers={"content-type": "application/json"}
            )
        if req.url.host == "json.example":
            return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})
        return httpx.Response(200, content=b"<html><body><div id=app></div></body></html>",
                              headers={"content-type": "text/html"})  # fmt: skip

    return httpx.MockTransport(handle)


def _deps(wb_body: bytes) -> Deps:
    f = HttpFetcher(resolve=lambda host: ["93.184.216.34"], transport=_transport(wb_body))
    return Deps(InMemoryStore(), None, f, InMemorySnapshots())  # type: ignore[arg-type]


JS_PORTAL = [
    Evidence(url="https://www.imf.org/x", title="imf.org", model_snippet="", confidence=0.9)
]


def test_detects_metric_and_countries_in_en_hinglish_hindi() -> None:
    assert metric_of("India ka per capita GDP Japan se zyada hai") == "NY.GDP.PCAP.CD"
    assert metric_of("India's GDP is bigger than the UK's") == "NY.GDP.MKTP.CD"
    assert metric_of("Pakistan mein mehngai zyada hai") == "FP.CPI.TOTL.ZG"
    assert metric_of("Biden closed more than 100 power plants") == ""
    assert countries_of("India per capita GDP is higher than Japan") == ["IND", "JPN"]
    assert countries_of("भारत की आबादी चीन से ज्यादा है") == ["IND", "CHN"]
    assert countries_of("he told us the plan") == []  # "us" is not a country here
    assert official_evidence("", "Biden closed more than 100 power plants") == []
    ev = official_evidence("bharat ki aabadi", "India's population is larger than China's")
    assert ev
    assert "IND;CHN" in ev[0].url
    assert "SP.POP.TOTL" in ev[0].url


def test_render_handles_bad_json() -> None:
    assert render(b"not json") == ""
    assert render(b'[{"page":1}]') == ""
    assert render(b'[{"page":1}, [{"value": null}, {"value": 1}]]') == ""
    body = _rows("SP.POP.TOTL", "Population, total", {"India": 1.46e9})
    assert "India: Population, total, 2025: 1,460,000,000.00" in render(body)


def test_comparison_card_proves_from_official_data() -> None:
    body = _rows(
        "NY.GDP.PCAP.CD", "GDP per capita (current US$)", {"India": 2702.48, "Japan": 35951.04}
    )
    for claim in (
        "India per capita GDP is higher than Japan",
        "India ka per capita GDP Japan se zyada hai",
    ):
        a = Assessment(
            Verdict.FALSE, "x", JS_PORTAL, claim_en="India's per capita GDP is higher than Japan's"
        )
        card = build_card(claim, a, _deps(body))
        assert card is not None
        assert str(card.sources[0].url).startswith("https://api.worldbank.org/")
        assert "Japan" in card.sources[0].snippet
        assert "35,951.04" in card.sources[0].snippet


def test_json_only_from_official_hosts_and_no_metric_no_change() -> None:
    body = _rows("NY.GDP.PCAP.CD", "GDP per capita (current US$)", {"India": 1.0})
    deps = _deps(body)
    j = [Evidence(url="https://json.example/a", title="", model_snippet="", confidence=1.0)]
    assert (
        build_card(
            "Biden closed more than 100 power plants", Assessment(Verdict.FALSE, "x", j), deps
        )
        is None
    )


def test_devanagari_metrics_and_country_figure() -> None:
    from app.officialdata import is_country_figure, metric_of

    assert metric_of("भारत की प्रति व्यक्ति आय जापान से अधिक है।") == "NY.GDP.PCAP.CD"
    assert metric_of("भारत की जीडीपी अमेरिका से बड़ी है") == "NY.GDP.MKTP.CD"
    assert metric_of("चीन की आबादी") == "SP.POP.TOTL"
    assert is_country_figure("India ki GDP America se badi hai")
    assert not is_country_figure("India is a great country")
    assert not is_country_figure("per capita income is rising")
