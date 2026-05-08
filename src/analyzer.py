"""Claude AI investment analysis for YouTube transcripts."""

import json
import os
import anthropic

SYSTEM_PROMPT = """你是一位專業的投資分析師助手，專門分析投資類 YouTube 影片的內容。
你能夠理解繁體中文、粵語，以及各種投資術語。

你的任務是從 YouTube 影片逐字稿中提取投資相關資訊，並產生結構化的投資策略分析。

分析時請注意：
- 準確識別提及的股票代號、ETF、加密貨幣等金融工具
- 區分 YouTuber 的個人觀點與客觀事實
- 標記風險提示和不確定性
- 所有輸出必須是繁體中文"""

ANALYSIS_PROMPT = """請分析以下 YouTube 影片逐字稿，提取投資相關資訊。

影片標題：{title}

逐字稿內容：
{transcript}

請以 JSON 格式回覆，結構如下：
{{
  "tickers": [
    {{
      "symbol": "股票代號或名稱",
      "type": "股票/ETF/加密貨幣/指數",
      "sentiment": "看多/看空/中性",
      "reason": "簡短說明原因"
    }}
  ],
  "sentiment": "整體市場情緒：看多/看空/中性",
  "market_outlook": "市場整體展望（2-3句話）",
  "key_points": [
    "重點1",
    "重點2",
    "重點3"
  ],
  "strategy": "建議投資策略（3-5句話，包含進出場時機、倉位管理）",
  "risks": [
    "風險1",
    "風險2"
  ],
  "time_horizon": "短線/中線/長線",
  "confidence": "高/中/低（對分析可信度的評估）",
  "disclaimer": "此分析僅供參考，不構成投資建議"
}}

只回覆 JSON，不要有其他文字。"""


def analyze_transcript(title: str, transcript: str) -> dict:
    """Send transcript to Claude and return structured investment analysis."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Trim transcript if too long (keep ~12k tokens worth)
    max_chars = 40000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n...[逐字稿已截斷]"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": ANALYSIS_PROMPT.format(title=title, transcript=transcript),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)
