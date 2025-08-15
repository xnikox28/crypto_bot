from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass
class Config:
    token: str
    poll_sec: int = 60
    db_path: str = "bot.db"

    @staticmethod
    def from_env() -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Falta BOT_TOKEN en .env")
        poll = int(os.getenv("POLL_SEC", "60"))
        db_path = os.getenv("DB_PATH", "bot.db")
        return Config(token=token, poll_sec=poll, db_path=db_path)
