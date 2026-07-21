import json
import re
import logging
from backend.config.settings import settings

logger = logging.getLogger(__name__)

_USE_CLAUDE = bool(settings.ANTHROPIC_API_KEY)

if _USE_CLAUDE:
    import anthropic as _anthropic
    _claude = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    _MODEL  = "claude-haiku-4-5-20251001"
    logger.info(f"LLM provider: Claude ({_MODEL})")
else:
    from groq import Groq as _Groq
    if not settings.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY chưa được set.")
    _groq  = _Groq(api_key=settings.GROQ_API_KEY)
    _MODEL = settings.MODEL_NAME
    logger.info(f"LLM provider: Groq ({_MODEL})")


def _call_llm(system_prompt: str, user_content: str, temperature: float = 0.1, json_mode: bool = True) -> str:
    if _USE_CLAUDE:
        sys_msg = system_prompt
        if json_mode:
            sys_msg += "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation."
        resp = _claude.messages.create(
            model=_MODEL,
            max_tokens=4096,
            temperature=temperature,   # was unset → Claude defaulted to 1.0 (high variance)
            system=sys_msg,
            messages=[{"role": "user", "content": user_content}],
        )
        usage = resp.usage
        logger.info(f"Claude tokens — input: {usage.input_tokens}, output: {usage.output_tokens}")
        return resp.content[0].text or ""
    else:
        # Thứ tự fallback khi gặp rate limit 429
        _FALLBACK_MODELS = [
            _MODEL,
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "deepseek-r1-distill-llama-70b",
            "llama-3.2-3b-preview",
        ]
        last_err = None
        for model in _FALLBACK_MODELS:
            try:
                kwargs: dict = dict(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content},
                    ],
                    temperature=temperature,
                )
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = _groq.chat.completions.create(**kwargs)
                if model != _MODEL:
                    logger.info(f"Groq fallback model used: {model}")
                return resp.choices[0].message.content or ""
            except Exception as e:
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    logger.warning(f"Groq 429 on {model}, trying next fallback...")
                    last_err = e
                    import time; time.sleep(2)
                    continue
                if "decommissioned" in str(e).lower() or "model_decommissioned" in str(e):
                    logger.warning(f"Groq model decommissioned: {model}, skipping")
                    last_err = e
                    continue
                raise
        raise RuntimeError(f"All Groq models rate-limited: {last_err}")


def _repair_json(raw: str) -> str:
    """
    Fix common LLM JSON malformations:
      1. Missing outer braces   →  "items": [...]  →  {"items": [...]}
      2. Trailing comma         →  {... ,}  →  {...}
      3. Truncated output       →  drop incomplete last item, close open structures
    """
    raw = raw.strip()
    if not raw:
        return "{}"

    # 1. Missing outer object — raw starts with a key like "items": [...]
    if raw[0] in ('"', "'"):
        raw = "{" + raw + "}"

    # 2. Remove trailing comma before closing bracket/brace
    raw = re.sub(r",\s*([}\]])", r"\1", raw)

    # Quick check — if already valid, return
    try:
        result = json.loads(raw)
        # Guard: if LLM returned a bare string like "items", parse succeeds
        # but we need a dict or list — not a plain string
        if isinstance(result, (dict, list)):
            return raw
    except json.JSONDecodeError:
        pass

    # 3. Truncated: truncate to the last complete `}` then close remaining structures
    raw = raw.rstrip()

    # If we only have a bare key like {"items"} (no value), treat as empty
    if re.fullmatch(r'\{\s*"[^"]*"\s*\}', raw):
        return '{"items": []}'

    last_close = raw.rfind("}")
    if last_close == -1:
        # No complete object at all — return minimal empty structure
        if '"items"' in raw or '"trim_items"' in raw:
            return '{"items": []}'
        return "{}"

    clean = raw[: last_close + 1]

    # Count unclosed brackets/braces in the truncated portion
    opens_bracket = clean.count("[") - clean.count("]")
    opens_brace   = clean.count("{") - clean.count("}")
    clean += "]" * max(opens_bracket, 0)
    clean += "}" * max(opens_brace, 0)

    # Strip trailing comma before any closing bracket/brace
    clean = re.sub(r",\s*([}\]])", r"\1", clean)

    return clean


class GroqClient:
    """LLM client — dùng Claude nếu có ANTHROPIC_API_KEY, fallback Groq."""

    def __init__(self):
        self.model = _MODEL

    def extract_json(self, system_prompt: str, user_content: str, temperature: float = 0.1) -> dict:
        raw = _call_llm(system_prompt, user_content, temperature, json_mode=True)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        # Attempt direct parse first — but reject bare strings/numbers
        try:
            result = json.loads(raw)
            if isinstance(result, (dict, list)):
                return result
            # Fall through to repair: LLM returned a bare string/number
        except json.JSONDecodeError:
            pass
        return json.loads(_repair_json(raw))

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.3) -> str:
        return _call_llm(system_prompt, user_content, temperature, json_mode=False)

    def extract_json_with_retry(
        self,
        system_prompt: str,
        user_content: str,
        max_retries: int = 2,
        temperature: float = 0.1,
    ) -> dict:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return self.extract_json(system_prompt, user_content, temperature + attempt * 0.1)
            except Exception as e:
                last_error = e
                logger.warning(f"extract_json attempt {attempt + 1} failed: {e}")
        raise ValueError(f"extract_json failed after {max_retries + 1} attempts: {last_error}")
