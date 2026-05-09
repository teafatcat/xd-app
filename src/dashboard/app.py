"""Flask web dashboard for investment analysis and chart generation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from flask import Flask, render_template, request, jsonify
from src.database import init_db, get_all_analyses
from src.data_fetcher import extract_tickers_from_text, fetch_multiple, get_current_prices
from src.charts import trend_chart, portfolio_chart, risk_return_chart, multi_trend_chart

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze_text", methods=["POST"])
def api_analyze_text():
    """Parse pasted analysis text, extract tickers, return chart data."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    manual_tickers = [t.strip().upper() for t in data.get("tickers", []) if t.strip()]
    allocations = data.get("allocations", [])  # [{ticker, pct, sentiment}]

    if not text and not manual_tickers:
        return jsonify({"error": "請貼上分析文字或輸入股票代號"}), 400

    # Extract tickers from text
    auto_tickers = extract_tickers_from_text(text) if text else []
    all_tickers = list(dict.fromkeys(manual_tickers + auto_tickers))  # dedupe, preserve order

    if not all_tickers:
        return jsonify({"error": "未能從文字中找到股票代號，請手動輸入"}), 400

    # Fetch price data
    try:
        tickers_data = fetch_multiple(all_tickers, period_days=90)
    except Exception as e:
        return jsonify({"error": f"抓取股價失敗：{e}"}), 500

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
    if allocations:
        valid_alloc = [a for a in allocations if a.get("ticker") in valid_tickers]
    else:
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
    app.run(debug=True, port=5000)
