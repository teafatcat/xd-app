"""OpenRouter AI investment analysis for YouTube transcripts."""

import json
import os
import re
from openai import OpenAI

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


DEFAULT_MODEL = "google/gemini-2.0-flash-exp:free"
MAX_TRANSCRIPT_CHARS = 40000
REQUEST_TIMEOUT_SECONDS = 120

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_LIST_FIELDS = ("tickers", "key_points", "risks")
_STR_FIELDS = ("sentiment", "market_outlook", "strategy", "time_horizon", "confidence", "disclaimer")


class AnalysisParseError(ValueError):
    """Raised when the LLM response cannot be turned into an analysis dict."""


def parse_llm_json(raw: str | None) -> dict:
    """Parse the LLM reply into a normalized analysis dict.

    Handles markdown code fences (with or without a language tag), leading or
    trailing prose around the JSON object, and missing/mistyped fields.
    Raises AnalysisParseError if no JSON object can be recovered.
    """
    if raw is None or not str(raw).strip():
        raise AnalysisParseError("LLM 回傳空白內容")
    text = str(raw).strip()

    candidates = [m.group(1).strip() for m in _FENCE_RE.finditer(text)]
    candidates.append(text)

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            # Fall back to the first decodable JSON object inside the text.
            obj = None
            start = candidate.find("{")
            while start != -1:
                try:
                    obj, _ = decoder.raw_decode(candidate, start)
                    break
                except json.JSONDecodeError:
                    start = candidate.find("{", start + 1)
        if isinstance(obj, dict):
            return normalize_analysis(obj)

    snippet = text[:200].replace("\n", " ")
    raise AnalysisParseError(f"無法解析 LLM 回傳的 JSON：{snippet}")


def normalize_analysis(obj: dict) -> dict:
    """Coerce fields to the types the rest of the app expects."""
    result = dict(obj)
    for field in _LIST_FIELDS:
        value = result.get(field)
        if value is None:
            value = []
        elif not isinstance(value, list):
            value = [value]
        result[field] = value

    tickers = []
    for t in result["tickers"]:
        if isinstance(t, dict):
            tickers.append(t)
        elif isinstance(t, str) and t.strip():
            tickers.append({"symbol": t.strip()})
    result["tickers"] = tickers
    result["key_points"] = [str(p) for p in result["key_points"] if p is not None]
    result["risks"] = [str(r) for r in result["risks"] if r is not None]

    for field in _STR_FIELDS:
        value = result.get(field)
        if value is not None and not isinstance(value, str):
            result[field] = str(value)
    return result


def analyze_transcript(title: str, transcript: str) -> dict:
    """Send transcript to OpenRouter and return structured investment analysis."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("未設定 OPENROUTER_API_KEY")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=2,
    )

    # Trim transcript if too long
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n...[逐字稿已截斷]"

    response = client.chat.completions.create(
        model=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ANALYSIS_PROMPT.format(title=title, transcript=transcript)},
        ],
        max_tokens=2048,
        temperature=0.2,
    )

    if not response.choices:
        raise AnalysisParseError("LLM 未回傳任何結果")
    return parse_llm_json(response.choices[0].message.content)
