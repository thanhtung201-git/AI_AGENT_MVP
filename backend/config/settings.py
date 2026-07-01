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

    # Supabase credentials
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")

settings = Settings()
