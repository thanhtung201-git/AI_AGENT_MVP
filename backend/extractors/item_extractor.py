import logging
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class ItemExtractor:
    """Extractor responsible for parsing the List of Items in a Purchase Order."""
    
    def __init__(self):
        self.groq_client = GroqClient()
        try:
            self.system_prompt = PromptManager.load_prompt("item_prompt.txt")
        except FileNotFoundError:
            logger.error("item_prompt.txt not found. Cannot initialize ItemExtractor.")
            raise

    def extract(self, raw_text: str) -> dict:
        """
        Executes the extraction process to find the items list.
        Returns a dict like: {"items": [{...}, {...}]}
        """
        if not raw_text or not raw_text.strip():
            return {"items": []}
            
        return self.groq_client.extract_json(
            system_prompt=self.system_prompt,
            user_content=raw_text
        )
