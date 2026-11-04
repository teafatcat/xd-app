import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.dashboard import app as app_module


def _df(n=30, start=100.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = np.linspace(start, start * 1.2, n)
    return pd.DataFrame(
        {"Open": close * 0.99, "High": close * 1.01, "Low": close * 0.98, "Close": close, "Volume": np.full(n, 1000)},
        index=idx,
    )


@pytest.fixture
def fetch(monkeypatch):
    """Mock all network access done by the route."""
    fetch_multiple = MagicMock(side_effect=lambda tickers, period_days=90: {t: _df() for t in tickers})
    prices = MagicMock(side_effect=lambda tickers: {t: 123.45 for t in tickers})
    monkeypatch.setattr(app_module, "fetch_multiple", fetch_multiple)
    monkeypatch.setattr(app_module, "get_current_prices", prices)
    return fetch_multiple


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def post(client, payload, **kw):
    return client.post("/api/analyze_text", data=json.dumps(payload), content_type="application/json", **kw)


def test_index_renders_with_security_headers(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "XD App".encode() in res.data
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"


def test_index_has_no_unescaped_inline_ticker_handlers(client):
    html = client.get("/").get_data(as_text=True)
    assert "onclick=\"removeTicker('${t}')\"" not in html
    assert "onclick=\"showTrend('${t}'" not in html
    assert "s.innerHTML = msg" not in html


def test_debug_disabled():
    assert app_module.app.debug is False


def test_analyze_manual_tickers(client, fetch):
    res = post(client, {"tickers": ["aapl", " msft "]})
    assert res.status_code == 200
    body = res.get_json()
    assert body["tickers"] == ["AAPL", "MSFT"]
    assert body["prices"] == {"AAPL": 123.45, "MSFT": 123.45}
    assert set(body["charts"]["trends"]) == {"AAPL", "MSFT"}
    for key in ("portfolio", "risk_return", "comparison"):
        json.loads(body["charts"][key])  # valid plotly JSON
    fetch.assert_called_once()


def test_analyze_extracts_from_text(client, fetch):
    res = post(client, {"text": "我看多AAPL股，買進2330.TW"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["auto_extracted"] == ["2330.TW", "AAPL"]
    assert "comparison" in body["charts"]


def test_single_ticker_has_no_comparison(client, fetch):
    body = post(client, {"tickers": ["AAPL"]}).get_json()
    assert "comparison" not in body["charts"]


@pytest.mark.parametrize("payload", [
    {},
    {"text": "", "tickers": []},
    {"text": "沒有任何代號的文字"},
])
def test_missing_input_400(client, fetch, payload):
    res = post(client, payload)
    assert res.status_code == 400
    assert "error" in res.get_json()
    fetch.assert_not_called()


@pytest.mark.parametrize("payload", [
    [1, 2],
    "string",
    {"text": 123},
    {"tickers": "AAPL"},
    {"tickers": ["<img src=x onerror=alert(1)>"]},
    {"tickers": ["AAPL'); alert(1);//"]},
])
def test_malformed_input_400_not_500(client, fetch, payload):
    res = post(client, payload)
    assert res.status_code == 400
    fetch.assert_not_called()


def test_non_json_body_400(client, fetch):
    res = client.post("/api/analyze_text", data="text=AAPL", content_type="application/x-www-form-urlencoded")
    assert res.status_code == 400
    fetch.assert_not_called()


def test_too_many_tickers_400(client, fetch):
    tickers = [f"T{i}" for i in range(app_module.MAX_TICKERS + 1)]
    assert post(client, {"tickers": tickers}).status_code == 400
    fetch.assert_not_called()


def test_text_too_long_400(client, fetch):
    assert post(client, {"text": "A" * (app_module.MAX_TEXT_CHARS + 1)}).status_code == 400


def test_oversized_body_413(client, fetch):
    res = post(client, {"text": "A" * (app_module.app.config["MAX_CONTENT_LENGTH"] + 10)})
    assert res.status_code == 413
    fetch.assert_not_called()


@pytest.mark.parametrize("sym", ["2330.TW", "0700.HK", "BRK-B", "BTC-USD", "^GSPC", "EURUSD=X"])
def test_valid_symbol_formats_accepted(client, fetch, sym):
    assert post(client, {"tickers": [sym]}).status_code == 200


def test_no_data_returns_400(client, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_multiple", MagicMock(return_value={}))
    assert post(client, {"tickers": ["ZZZZ"]}).status_code == 400


def test_fetch_exception_does_not_leak_details(client, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_multiple", MagicMock(side_effect=RuntimeError("secret /internal/path")))
    res = post(client, {"tickers": ["AAPL"]})
    assert res.status_code == 500
    assert "secret" not in res.get_data(as_text=True)


def test_allocations_are_sanitized(client, fetch):
    res = post(client, {
        "tickers": ["AAPL", "MSFT"],
        "allocations": [
            {"ticker": "AAPL", "pct": "60", "sentiment": "看多"},
            {"ticker": "MSFT", "pct": "abc"},
            "garbage",
            {"ticker": "NOTVALID", "pct": 10},
            {"ticker": "MSFT", "pct": -5},
        ],
    })
    assert res.status_code == 200
    pie = json.loads(res.get_json()["charts"]["portfolio"])["data"][0]
    assert list(pie["labels"]) == ["AAPL"]


def test_bad_allocations_fall_back_to_equal_weight(client, fetch):
    res = post(client, {"tickers": ["AAPL", "MSFT"], "allocations": "nope"})
    pie = json.loads(res.get_json()["charts"]["portfolio"])["data"][0]
    assert list(pie["labels"]) == ["AAPL", "MSFT"]


def test_nan_price_serialized_as_null(client, monkeypatch, fetch):
    from src import data_fetcher

    fake = MagicMock()
    fake.return_value.fast_info.last_price = float("nan")
    monkeypatch.setattr(data_fetcher.yf, "Ticker", fake)
    monkeypatch.setattr(app_module, "get_current_prices", data_fetcher.get_current_prices)
    res = post(client, {"tickers": ["AAPL"]})
    assert "NaN" not in res.get_data(as_text=True)
    assert res.get_json()["prices"]["AAPL"] is None


def test_get_not_allowed(client):
    assert client.get("/api/analyze_text").status_code == 405
