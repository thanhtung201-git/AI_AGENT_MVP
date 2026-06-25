import logging
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class HeaderExtractor:
    """Extractor responsible for parsing the Header Information of a Purchase Order."""
    
    def __init__(self):
        self.groq_client = GroqClient()
        
        # Load the specialized prompt for header extraction
        try:
            self.system_prompt = PromptManager.load_prompt("header_prompt.txt")
        except FileNotFoundError:
            logger.error("header_prompt.txt not found. Cannot initialize HeaderExtractor.")
            raise

    def extract(self, raw_text: str) -> dict:
        """
        Executes the extraction process on the raw text.
        
        Args:
            raw_text: The string content extracted from PDF/Word/Excel.
            
        Returns:
            A dictionary containing the extracted header fields.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty raw text provided for header extraction.")
            return {}
            
        return self.groq_client.extract_json(
            system_prompt=self.system_prompt,
            user_content=raw_text
        )
