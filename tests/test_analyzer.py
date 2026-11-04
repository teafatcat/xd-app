import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src import analyzer
from src.analyzer import AnalysisParseError, parse_llm_json

VALID = {
    "tickers": [{"symbol": "NVDA", "type": "股票", "sentiment": "看多", "reason": "AI"}],
    "sentiment": "看多",
    "market_outlook": "正面",
    "key_points": ["k1"],
    "strategy": "s",
    "risks": ["r1"],
    "time_horizon": "長線",
    "confidence": "中",
    "disclaimer": "d",
}
VALID_TEXT = json.dumps(VALID, ensure_ascii=False)


@pytest.mark.parametrize("raw", [
    VALID_TEXT,
    f"```json\n{VALID_TEXT}\n```",
    f"```JSON\n{VALID_TEXT}\n```",
    f"```\n{VALID_TEXT}\n```",
    f"以下是分析結果：\n```json\n{VALID_TEXT}\n```\n希望有幫助！",
    f"好的，結果如下 {VALID_TEXT} 以上。",
    f"  \n{VALID_TEXT}\n  ",
])
def test_parse_valid_variants(raw):
    assert parse_llm_json(raw) == VALID


def test_parse_braces_inside_strings():
    obj = {**VALID, "strategy": "注意 {不是 JSON} 與 ``` 符號"}
    assert parse_llm_json("前言 " + json.dumps(obj, ensure_ascii=False))["strategy"] == obj["strategy"]


@pytest.mark.parametrize("raw", [None, "", "   ", "抱歉，我無法分析", "{\"tickers\": [", "[1, 2, 3]", "\"just a string\""])
def test_parse_invalid_raises(raw):
    with pytest.raises(AnalysisParseError):
        parse_llm_json(raw)


def test_parse_error_is_value_error():
    assert issubclass(AnalysisParseError, ValueError)


def test_normalizes_missing_and_wrong_types():
    out = parse_llm_json(json.dumps({
        "tickers": ["AAPL", {"symbol": "TSLA"}, 5, ""],
        "key_points": "單一重點",
        "risks": None,
        "confidence": 0.8,
    }))
    assert out["tickers"] == [{"symbol": "AAPL"}, {"symbol": "TSLA"}]
    assert out["key_points"] == ["單一重點"]
    assert out["risks"] == []
    assert out["confidence"] == "0.8"


def _fake_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    ctor = MagicMock(return_value=client)
    monkeypatch.setattr(analyzer, "OpenAI", ctor)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    return ctor, client


def test_analyze_transcript_uses_mocked_client(fake_client):
    ctor, client = fake_client
    client.chat.completions.create.return_value = _fake_response(f"```json\n{VALID_TEXT}\n```")

    assert analyzer.analyze_transcript("標題", "逐字稿") == VALID

    kwargs = ctor.call_args.kwargs
    assert kwargs["api_key"] == "test-key"
    assert kwargs["timeout"] == analyzer.REQUEST_TIMEOUT_SECONDS
    call = client.chat.completions.create.call_args.kwargs
    assert call["model"] == analyzer.DEFAULT_MODEL
    assert "標題" in call["messages"][1]["content"]


def test_analyze_transcript_model_override(fake_client, monkeypatch):
    _, client = fake_client
    monkeypatch.setenv("OPENROUTER_MODEL", "some/other-model")
    client.chat.completions.create.return_value = _fake_response(VALID_TEXT)
    analyzer.analyze_transcript("t", "x")
    assert client.chat.completions.create.call_args.kwargs["model"] == "some/other-model"


def test_analyze_transcript_truncates_long_input(fake_client):
    _, client = fake_client
    client.chat.completions.create.return_value = _fake_response(VALID_TEXT)
    analyzer.analyze_transcript("t", "字" * (analyzer.MAX_TRANSCRIPT_CHARS + 500))
    prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "逐字稿已截斷" in prompt
    assert prompt.count("字") < analyzer.MAX_TRANSCRIPT_CHARS + 100


def test_title_with_braces_does_not_break_prompt(fake_client):
    _, client = fake_client
    client.chat.completions.create.return_value = _fake_response(VALID_TEXT)
    analyzer.analyze_transcript("{title} {0} }{", "x")
    assert "{title} {0} }{" in client.chat.completions.create.call_args.kwargs["messages"][1]["content"]


@pytest.mark.parametrize("response", [_fake_response(None), SimpleNamespace(choices=[])])
def test_analyze_transcript_empty_response(fake_client, response):
    _, client = fake_client
    client.chat.completions.create.return_value = response
    with pytest.raises(AnalysisParseError):
        analyzer.analyze_transcript("t", "x")


def test_analyze_transcript_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(analyzer, "OpenAI", MagicMock(side_effect=AssertionError("must not be called")))
    with pytest.raises(RuntimeError):
        analyzer.analyze_transcript("t", "x")
