import logging
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class SizeExtractor:
    """Extractor responsible for parsing the Size Breakdown for specific items."""
    
    def __init__(self):
        self.groq_client = GroqClient()
        try:
            self.system_prompt = PromptManager.load_prompt("size_prompt.txt")
        except FileNotFoundError:
            logger.error("size_prompt.txt not found. Cannot initialize SizeExtractor.")
            raise

    def extract(self, raw_text: str, style_code: str) -> dict:
        """
        Extracts size breakdown for a given style code.
        Returns a dict like: {"size_breakdown": {"S": 10, "M": 20}}
        """
        if not raw_text or not style_code:
            return {"size_breakdown": {}}
            
        user_content = f"Find sizes for Style Code: {style_code}\n\nRAW TEXT:\n{raw_text}"
        
        return self.groq_client.extract_json(
            system_prompt=self.system_prompt,
            user_content=user_content
        )
