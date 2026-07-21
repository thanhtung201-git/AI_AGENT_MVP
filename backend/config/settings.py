import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

# Đọc trực tiếp sau khi load_dotenv để tránh class attribute bị cache
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL       = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY       = os.environ.get("SUPABASE_KEY", "")
GMAIL_USER              = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD      = os.environ.get("GMAIL_APP_PASSWORD", "")
TELEGRAM_BOT_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_DEFAULT_CHAT_ID = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "")

_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPTS_DIR = os.path.join(_BASE_DIR, "prompts")

# Batch GO Upload template — the company's fixed-schema ERP import file. The
# generator fills this in place instead of building a workbook from scratch.
# Overridable via env for a different customer/template.
_BATCH_GO_TEMPLATE = os.environ.get(
    "BATCH_GO_TEMPLATE",
    os.path.join(_BASE_DIR, "go_compare", "templates", "batch_go_template.xlsx"),
)


class Settings:
    GROQ_API_KEY:       str = GROQ_API_KEY
    ANTHROPIC_API_KEY:  str = ANTHROPIC_API_KEY
    OPENROUTER_API_KEY: str = OPENROUTER_API_KEY
    GEMINI_API_KEY:     str = GEMINI_API_KEY
    # 8b-instant has far higher free-tier limits than 70b → fewer 429s per run.
    # Override with GROQ_MODEL=llama-3.3-70b-versatile for higher quality if quota allows.
    MODEL_NAME:         str = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    BASE_DIR:           str = _BASE_DIR
    PROMPTS_DIR:        str = _PROMPTS_DIR
    BATCH_GO_TEMPLATE:  str = _BATCH_GO_TEMPLATE
    SUPABASE_URL:       str = SUPABASE_URL
    SUPABASE_KEY:       str = SUPABASE_KEY
    GMAIL_USER:               str = GMAIL_USER
    GMAIL_APP_PASSWORD:       str = GMAIL_APP_PASSWORD
    TELEGRAM_BOT_TOKEN:       str = TELEGRAM_BOT_TOKEN
    TELEGRAM_DEFAULT_CHAT_ID: str = TELEGRAM_DEFAULT_CHAT_ID


settings = Settings()
