import json
import os
import re
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. "
                "Copy .env.example → .env and add your key."
            )
        _client = OpenAI(api_key=api_key)
    return _client


SYSTEM_PROMPT = "You are an AI trading agent. Respond ONLY with valid JSON."

USER_TEMPLATE = """
Based on the following market indicators for {ticker}:

  Price       : {price}
  RSI (14)    : {rsi}
  MA20        : {ma20}
  MA50        : {ma50}
  MACD        : {macd}
  MACD Signal : {macd_signal}
  MACD Hist   : {macd_diff}
  BB Upper    : {bb_upper}
  BB Lower    : {bb_lower}
  BB Mid      : {bb_mid}

User preferences:
  Trading style : {style}
  Risk level    : {risk}
  Market        : {market}
  Universe      : {stock_universe}
  Current Position:
    {position_summary}

Decide ONE action: BUY, SELL, or HOLD.
If there is an open position and momentum clearly reverses against it, prefer exiting.

Respond strictly in this JSON format (no extra text):
{{
  "decision":   "BUY" | "SELL" | "HOLD",
  "confidence": <integer 0-100>,
  "reason":     "<one-sentence explanation>"
}}
""".strip()


def get_trading_decision(indicators: dict, settings: dict, position_context: dict | None = None) -> dict:
    """
    Send indicator data + user settings to OpenAI and return the parsed
    decision dict: {decision, confidence, reason}.
    """
    if position_context:
        position_summary = (
            f"side={position_context.get('side')}, "
            f"qty={position_context.get('quantity')}, "
            f"avg_cost={position_context.get('avg_cost')}, "
            f"unrealized_pct={position_context.get('unrealized_pct')}"
        )
    else:
        position_summary = "no open position"

    prompt = USER_TEMPLATE.format(
        ticker=indicators["ticker"],
        price=indicators["price"],
        rsi=indicators["rsi"],
        ma20=indicators["ma20"],
        ma50=indicators["ma50"],
        macd=indicators.get("macd", "N/A"),
        macd_signal=indicators.get("macd_signal", "N/A"),
        macd_diff=indicators.get("macd_diff", "N/A"),
        bb_upper=indicators.get("bb_upper", "N/A"),
        bb_lower=indicators.get("bb_lower", "N/A"),
        bb_mid=indicators.get("bb_mid", "N/A"),
        style=settings.get("style", "short_term"),
        risk=settings.get("risk", "medium"),
        market=settings.get("market", "indian_stocks"),
        stock_universe=settings.get("stock_universe", "nifty_50"),
        position_summary=position_summary,
    )

    client = _get_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    response = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )
            break
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            retryable = "rate" in msg or "429" in msg or "timeout" in msg or "temporarily" in msg
            if attempt == 2 or not retryable:
                raise
            time.sleep(min(8.0, 1.0 * (2**attempt)))
    if response is None:
        raise RuntimeError(f"OpenAI response missing after retries: {last_exc}")

    raw = response.choices[0].message.content.strip()

    # Strip possible markdown fences (opening and closing)
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI returned invalid JSON: {exc}. Raw: {raw!r}") from exc

    # Normalise fields
    result["decision"]   = result["decision"].upper()
    result["confidence"] = int(result.get("confidence", 50))
    result["reason"]     = result.get("reason", "")

    if result["decision"] not in {"BUY", "SELL", "HOLD"}:
        raise ValueError(f"Unexpected decision value: {result['decision']}")

    return result
