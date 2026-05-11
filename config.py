import os


# -----------------------------------------------------------------------------
# Variáveis de ambiente
# -----------------------------------------------------------------------------

API_TOKEN = os.getenv("API_TOKEN", "changeme")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")  # opcional: service account

BASE_URL = os.getenv("BASE_URL", "https://agente-planejamento.onrender.com").rstrip("/")
REDIRECT_URI = f"{BASE_URL}/oauth/callback"

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "America/Sao_Paulo")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
