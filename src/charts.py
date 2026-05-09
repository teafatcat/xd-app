"""Generate investment charts using plotly."""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import json


def _fig_to_json(fig) -> str:
    return fig.to_json()


def trend_chart(ticker: str, df: pd.DataFrame, signals: list[dict] | None = None) -> str:
    """K-line + volume chart with optional buy/sell signals."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.03)

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"].squeeze(),
        high=df["High"].squeeze(),
        low=df["Low"].squeeze(),
        close=df["Close"].squeeze(),
        name=ticker,
        increasing_line_color="#4ade80",
        decreasing_line_color="#f87171",
    ), row=1, col=1)

    # Volume
    colors = ["#4ade80" if c >= o else "#f87171"
              for c, o in zip(df["Close"].squeeze(), df["Open"].squeeze())]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"].squeeze(),
        marker_color=colors, name="成交量", showlegend=False,
    ), row=2, col=1)

    # Buy/sell signal markers
    if signals:
        buys = [s for s in signals if s.get("action") == "buy"]
        sells = [s for s in signals if s.get("action") == "sell"]
        if buys:
            fig.add_trace(go.Scatter(
                x=[s["date"] for s in buys],
                y=[s["price"] for s in buys],
                mode="markers", marker=dict(symbol="triangle-up", size=14, color="#4ade80"),
                name="買入", showlegend=True,
            ), row=1, col=1)
        if sells:
            fig.add_trace(go.Scatter(
                x=[s["date"] for s in sells],
                y=[s["price"] for s in sells],
                mode="markers", marker=dict(symbol="triangle-down", size=14, color="#f87171"),
                name="賣出", showlegend=True,
            ), row=1, col=1)

    fig.update_layout(**_dark_layout(f"{ticker} 走勢圖"))
    fig.update_xaxes(rangeslider_visible=False)
    return _fig_to_json(fig)


def portfolio_chart(allocations: list[dict]) -> str:
    """Pie chart of portfolio allocation. allocations = [{ticker, pct, sentiment}]"""
    colors = []
    for a in allocations:
        s = a.get("sentiment", "")
        if s == "看多":
            colors.append("#4ade80")
        elif s == "看空":
            colors.append("#f87171")
        else:
            colors.append("#60a5fa")

    fig = go.Figure(go.Pie(
        labels=[a["ticker"] for a in allocations],
        values=[a["pct"] for a in allocations],
        marker_colors=colors,
        textinfo="label+percent",
        hole=0.4,
    ))
    fig.update_layout(**_dark_layout("投資組合配置"))
    return _fig_to_json(fig)


def risk_return_chart(tickers_data: dict[str, pd.DataFrame]) -> str:
    """Scatter plot of annualized return vs volatility for each ticker."""
    points = []
    for ticker, df in tickers_data.items():
        close = df["Close"].squeeze()
        if len(close) < 5:
            continue
        daily_ret = close.pct_change().dropna()
        ann_ret = float(daily_ret.mean() * 252 * 100)
        ann_vol = float(daily_ret.std() * (252 ** 0.5) * 100)
        points.append({"ticker": ticker, "return": ann_ret, "vol": ann_vol})

    if not points:
        fig = go.Figure()
        fig.update_layout(**_dark_layout("風險報酬分析"))
        return _fig_to_json(fig)

    fig = go.Figure()
    for p in points:
        fig.add_trace(go.Scatter(
            x=[p["vol"]], y=[p["return"]],
            mode="markers+text",
            text=[p["ticker"]],
            textposition="top center",
            marker=dict(size=16, color="#6366f1"),
            name=p["ticker"],
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="#475569")
    fig.update_layout(
        **_dark_layout("風險報酬分析"),
        xaxis_title="波動率 % (年化)",
        yaxis_title="報酬率 % (年化)",
        showlegend=False,
    )
    return _fig_to_json(fig)


def multi_trend_chart(tickers_data: dict[str, pd.DataFrame]) -> str:
    """Normalized price performance comparison of multiple tickers."""
    fig = go.Figure()
    palette = ["#6366f1", "#4ade80", "#f87171", "#fbbf24", "#60a5fa", "#a78bfa"]

    for i, (ticker, df) in enumerate(tickers_data.items()):
        close = df["Close"].squeeze()
        normalized = (close / close.iloc[0] * 100).round(2)
        fig.add_trace(go.Scatter(
            x=df.index, y=normalized,
            name=ticker,
            line=dict(color=palette[i % len(palette)], width=2),
        ))

    fig.add_hline(y=100, line_dash="dash", line_color="#475569", opacity=0.5)
    fig.update_layout(**_dark_layout("相對表現比較 (基準=100)"))
    return _fig_to_json(fig)


def _dark_layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(color="#f1f5f9", size=16)),
        paper_bgcolor="#1e293b",
        plot_bgcolor="#0f172a",
        font=dict(color="#94a3b8"),
        xaxis=dict(gridcolor="#1e3a5f", showgrid=True),
        yaxis=dict(gridcolor="#1e3a5f", showgrid=True),
        margin=dict(l=40, r=20, t=50, b=40),
        height=400,
    )
