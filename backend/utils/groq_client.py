import json
import logging
from groq import Groq
from backend.config.settings import settings

logger = logging.getLogger(__name__)

class GroqClient:
    """A wrapper client for the Groq API to enforce JSON extraction."""
    
    def __init__(self):
        if not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY is not set in environment variables.")
        
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = settings.MODEL_NAME

    def extract_json(self, system_prompt: str, user_content: str) -> dict:
        """
        Sends a prompt to Groq API and strictly returns a parsed JSON dictionary.
        
        Args:
            system_prompt: The instructions and JSON schema for the LLM.
            user_content: The raw text extracted from the document.
            
        Returns:
            A dictionary parsed from the LLM's JSON output.
        """
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for deterministic extraction
            )
            
            raw_json_str = response.choices[0].message.content
            return json.loads(raw_json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from Groq response: {e}")
            raise ValueError(f"Groq did not return valid JSON: {e}")
        except Exception as e:
            logger.error(f"Groq API Error: {e}")
            raise
