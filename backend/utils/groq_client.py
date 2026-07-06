import json
import re
import logging
from groq import Groq
from backend.config.settings import settings

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self):
        if not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY chưa được set.")
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = settings.MODEL_NAME

    def extract_json(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.1,
    ) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        return json.loads(raw)

    def chat(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.3,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content

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
