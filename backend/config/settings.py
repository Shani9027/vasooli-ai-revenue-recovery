import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_file = Path(__file__).parent.parent / ".env"
load_dotenv(env_file)


class Settings:
    """Application settings"""
    
    # App
    APP_NAME = "Vasooli - AI Revenue Recovery Agent"
    APP_VERSION = "0.1.0"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vasooli.db")
    
    # Paths
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    BACKEND_ROOT = Path(__file__).parent.parent
    DB_PATH = BACKEND_ROOT / "vasooli.db"
    AUDIT_LOG_PATH = BACKEND_ROOT / "audit.jsonl"

    # Razorpay Test Mode (Optional)
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")


settings = Settings()
