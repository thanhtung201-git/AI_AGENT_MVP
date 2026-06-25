import os
from backend.config.settings import settings

class PromptManager:
    """Utility class to manage loading text-based prompts from the file system."""
    
    @staticmethod
    def load_prompt(filename: str) -> str:
        """
        Loads a prompt from a text file in the prompts directory.
        
        Args:
            filename: Name of the prompt file (e.g., 'system_prompt.txt')
            
        Returns:
            The string content of the file.
        """
        filepath = os.path.join(settings.PROMPTS_DIR, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Prompt file not found: {filepath}")
            
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
