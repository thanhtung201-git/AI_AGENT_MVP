import json
import logging
from groq import Groq
from backend.config.settings import settings

logger = logging.getLogger(__name__)


class GroqClient:
    """
    Wrapper cho Groq API.
    Hỗ trợ 2 mode:
    - extract_json: Trả về JSON có cấu trúc (dùng cho extraction, planning, review)
    - chat: Trả về text thuần (dùng cho conversational tasks)
    """

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
        """
        Gọi LLM và enforce trả về JSON hợp lệ.
        Dùng cho: extraction, planning, review.

        Args:
            system_prompt: Hướng dẫn + schema cho LLM
            user_content: Nội dung cần xử lý
            temperature: Thấp = deterministic hơn (mặc định 0.1)

        Returns:
            dict parsed từ JSON output của LLM
        """
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            raw = response.choices[0].message.content
            return json.loads(raw)

        except json.JSONDecodeError as e:
            logger.error(f"LLM không trả về JSON hợp lệ: {e}")
            raise ValueError(f"Invalid JSON from LLM: {e}")
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise

    def chat(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.3,
    ) -> str:
        """
        Gọi LLM và trả về text thuần.
        Dùng cho: conversational responses, explanations.

        Returns:
            str — nội dung phản hồi của LLM
        """
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                model=self.model,
                temperature=temperature,
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Groq chat API error: {e}")
            raise

    def extract_json_with_retry(
        self,
        system_prompt: str,
        user_content: str,
        max_retries: int = 2,
        temperature: float = 0.1,
    ) -> dict:
        """
        extract_json với tự động retry nếu JSON parse fail.
        Mỗi lần retry tăng temperature để LLM không lặp lại cùng output lỗi.
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return self.extract_json(system_prompt, user_content, temperature + attempt * 0.1)
            except (ValueError, Exception) as e:
                last_error = e
                logger.warning(f"extract_json attempt {attempt + 1} failed: {e}")

        raise ValueError(f"extract_json failed after {max_retries + 1} attempts: {last_error}")