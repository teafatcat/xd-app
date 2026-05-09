"""Fetch stock price data via yfinance."""

import re
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def extract_tickers_from_text(text: str) -> list[str]:
    """Simple regex extraction of stock tickers from analysis text."""
    # Common patterns: US stocks (AAPL), TW stocks (2330.TW or 2330), HK (0700.HK)
    patterns = [
        r'\b([A-Z]{1,5})\b(?=\s*(?:股|ETF|漲|跌|看多|看空|買|賣|\$|USD))',  # US with context
        r'\b(\d{4}\.TW)\b',   # TW format
        r'\b(\d{4}\.HK)\b',   # HK format
        r'\$([A-Z]{1,5})\b',  # $TICKER format
    ]
    found = set()
    for p in patterns:
        found.update(re.findall(p, text))

    # Also find standalone known ETFs and indices
    etf_pattern = r'\b(QQQ|SPY|VOO|VTI|GLD|TLT|IWM|DIA|ARKK|SOXL|TQQQ|UVXY)\b'
    found.update(re.findall(etf_pattern, text))

    return sorted(found)


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
            info = yf.Ticker(t).fast_info
            prices[t] = round(info.last_price, 2)
        except Exception:
            prices[t] = None
    return prices
