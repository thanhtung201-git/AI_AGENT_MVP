import os

class Settings:
    # Get API key from environment, or set a placeholder
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "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")
    
    # Recommended Groq Llama model for complex JSON extraction tasks
    MODEL_NAME: str = "llama-3.3-70b-versatile"
    
    # Base path to the backend directory
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Path to the prompts directory
    PROMPTS_DIR: str = os.path.join(BASE_DIR, "prompts")

settings = Settings()
