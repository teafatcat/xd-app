"""Fetch stock price data via yfinance."""

import math
import re
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


# Python's \b treats CJK characters as word characters, so "AAPL股" or "買進2330.TW"
# has no word boundary next to the ticker. Use ASCII-only look-arounds instead.
_L = r"(?<![A-Za-z0-9.])"
_R = r"(?![A-Za-z0-9])"

# Words the context pattern would otherwise pick up as tickers (e.g. "ETF 漲").
_NOT_TICKERS = {"ETF", "USD"}


def extract_tickers_from_text(text: str) -> list[str]:
    """Simple regex extraction of stock tickers from analysis text."""
    # Common patterns: US stocks (AAPL), TW stocks (2330.TW), HK (0700.HK)
    patterns = [
        _L + r"([A-Z]{1,5})" + _R + r"(?=\s*(?:股|ETF|漲|跌|看多|看空|買|賣|\$|USD))",  # US with context
        _L + r"(\d{4}\.TW)" + _R,   # TW format
        _L + r"(\d{4}\.HK)" + _R,   # HK format
        r"\$([A-Z]{1,5})" + _R,     # $TICKER format
    ]
    found = set()
    for p in patterns:
        found.update(re.findall(p, text))

    # Also find standalone known ETFs and indices
    etf_pattern = _L + r"(QQQ|SPY|VOO|VTI|GLD|TLT|IWM|DIA|ARKK|SOXL|TQQQ|UVXY)" + _R
    found.update(re.findall(etf_pattern, text))

    return sorted(found - _NOT_TICKERS)


def fetch_stock_data(ticker: str, period_days: int = 90) -> pd.DataFrame:
    """Fetch OHLCV data for a ticker."""
    end = datetime.today()
    start = end - timedelta(days=period_days)
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data found for {ticker}")
    df.index = pd.to_datetime(df.index)
    return df


def fetch_multiple(tickers: list[str], period_days: int = 90) -> dict[str, pd.DataFrame]:
    """Fetch data for multiple tickers, skip ones that fail."""
    result = {}
    for t in tickers:
        try:
            result[t] = fetch_stock_data(t, period_days)
        except Exception:
            pass
    return result


def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Get latest closing price for each ticker."""
    prices = {}
    for t in tickers:
        try:
            price = float(yf.Ticker(t).fast_info.last_price)
            # NaN/inf would serialize as invalid JSON in the API response.
            prices[t] = round(price, 2) if math.isfinite(price) else None
        except Exception:
            prices[t] = None
    return prices
