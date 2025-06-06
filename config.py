import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value

def get_optional_env(key: str, default: Any) -> Any:
    return os.getenv(key, default)

BOT_TOKEN: str = get_required_env("BOT_TOKEN")

DB_HOST: str = get_optional_env("DB_HOST", "localhost")
DB_PORT: int = int(get_optional_env("DB_PORT", 5432))
DB_NAME: str = get_optional_env("DB_NAME", "battlestudy")
DB_USER: str = get_optional_env("DB_USER", "postgres")
DB_PASS: str = get_optional_env("DB_PASS", "postgres")

TIMEOUT_SETTINGS: Dict[str, int] = {
    "easy": 60,
    "medium": 180,
    "hard": 300
}

RATING_CHANGES: Dict[str, Dict[str, int]] = {
    "easy": {"win": 10, "lose": -5},
    "medium": {"win": 25, "lose": -15},
    "hard": {"win": 50, "lose": -35}
}