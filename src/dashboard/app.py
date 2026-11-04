"""Flask web dashboard for investment analysis and chart generation."""

import logging
import math
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from flask import Flask, render_template, request, jsonify
from src.database import init_db, get_all_analyses
from src.data_fetcher import extract_tickers_from_text, fetch_multiple, get_current_prices
from src.charts import trend_chart, portfolio_chart, risk_return_chart, multi_trend_chart

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # reject oversized request bodies (413)

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 50_000
MAX_TICKERS = 10
# Yahoo symbols: AAPL, 2330.TW, 0700.HK, BRK-B, BTC-USD, ^GSPC, EURUSD=X
TICKER_RE = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-=]{0,14}$")


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


def _bad_request(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _clean_allocations(raw, valid_tickers: list[str]) -> list[dict]:
    """Keep only well-formed allocation entries for tickers we have data for."""
    if not isinstance(raw, list):
        return []
    cleaned = []
    for a in raw:
        if not isinstance(a, dict) or a.get("ticker") not in valid_tickers:
            continue
        try:
            pct = float(a.get("pct"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(pct) or pct <= 0:
            continue
        sentiment = a.get("sentiment")
        cleaned.append({
            "ticker": a["ticker"],
            "pct": pct,
            "sentiment": sentiment if isinstance(sentiment, str) else "中性",
        })
    return cleaned


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze_text", methods=["POST"])
def api_analyze_text():
    """Parse pasted analysis text, extract tickers, return chart data."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("請求格式錯誤，需為 JSON 物件")

    text = data.get("text") or ""
    raw_tickers = data.get("tickers") or []
    if not isinstance(text, str) or not isinstance(raw_tickers, list):
        return _bad_request("text 必須是字串、tickers 必須是陣列")
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        return _bad_request(f"文字過長（上限 {MAX_TEXT_CHARS} 字）")

    manual_tickers = []
    for t in raw_tickers:
        if not isinstance(t, str) or not t.strip():
            continue
        t = t.strip().upper()
        if not TICKER_RE.match(t):
            return _bad_request(f"股票代號格式不正確：{t[:20]}")
        manual_tickers.append(t)
    allocations = data.get("allocations", [])  # [{ticker, pct, sentiment}]

    if not text and not manual_tickers:
        return _bad_request("請貼上分析文字或輸入股票代號")

    # Extract tickers from text
    auto_tickers = extract_tickers_from_text(text) if text else []
    all_tickers = list(dict.fromkeys(manual_tickers + auto_tickers))  # dedupe, preserve order

    if not all_tickers:
        return _bad_request("未能從文字中找到股票代號，請手動輸入")
    if len(all_tickers) > MAX_TICKERS:
        return _bad_request(f"股票代號過多（上限 {MAX_TICKERS} 檔），請減少後再試")

    # Fetch price data
    try:
        tickers_data = fetch_multiple(all_tickers, period_days=90)
    except Exception:
        logger.exception("fetch_multiple failed")
        return jsonify({"error": "抓取股價失敗，請稍後再試"}), 500

    if not tickers_data:
        return jsonify({"error": "無法取得任何股票數據，請確認代號格式（美股：AAPL，台股：2330.TW）"}), 400

    valid_tickers = list(tickers_data.keys())
    prices = get_current_prices(valid_tickers)

    # Generate charts
    charts = {}

    # 1. Individual trend charts (first 4 tickers)
    trend_charts = {}
    for t in valid_tickers[:4]:
        try:
            trend_charts[t] = trend_chart(t, tickers_data[t])
        except Exception:
            pass
    charts["trends"] = trend_charts

    # 2. Portfolio allocation
    valid_alloc = _clean_allocations(allocations, valid_tickers)
    if not valid_alloc:
        equal_pct = round(100 / len(valid_tickers), 1)
        valid_alloc = [{"ticker": t, "pct": equal_pct, "sentiment": "中性"} for t in valid_tickers]

    try:
        charts["portfolio"] = portfolio_chart(valid_alloc)
    except Exception:
        charts["portfolio"] = None

    # 3. Risk/return scatter
    try:
        charts["risk_return"] = risk_return_chart(tickers_data)
    except Exception:
        charts["risk_return"] = None

    # 4. Multi-ticker comparison
    if len(valid_tickers) > 1:
        try:
            charts["comparison"] = multi_trend_chart(tickers_data)
        except Exception:
            charts["comparison"] = None

    return jsonify({
        "tickers": valid_tickers,
        "prices": prices,
        "charts": charts,
        "auto_extracted": auto_tickers,
    })


if __name__ == "__main__":
    init_db()
    # Never enable the Werkzeug debugger by default: it allows arbitrary code execution.
    # Opt in explicitly with FLASK_DEBUG=1 for local development only.
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
