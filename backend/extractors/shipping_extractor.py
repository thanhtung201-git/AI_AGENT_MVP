import logging
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class ShippingExtractor:
    """Extractor for Shipping, Payment, and Notes."""
    
    def __init__(self):
        self.groq_client = GroqClient()
        try:
            self.system_prompt = PromptManager.load_prompt("shipping_prompt.txt")
        except FileNotFoundError:
            logger.error("shipping_prompt.txt not found. Cannot initialize ShippingExtractor.")
            raise

    def extract(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            return {}
            
        return self.groq_client.extract_json(
            system_prompt=self.system_prompt,
            user_content=raw_text
        )
