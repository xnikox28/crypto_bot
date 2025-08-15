# bot/main.py
from __future__ import annotations
import sys
import asyncio
from dotenv import load_dotenv

from .utils.logging import setup_logging
from .logging_setup import setup_logging
from .utils.warnings import silence_pkg_resources_warning
from .config import Config
from .tz_guard import ensure_apscheduler_tz_compat
from .db import repo
from .app import build_app

def main() -> None:
    # Logging + env
    setup_logging()
    silence_pkg_resources_warning()
    load_dotenv()

    # Asegura compatibilidad tz (apscheduler + pytz)
    ensure_apscheduler_tz_compat()

    # Config
    cfg = Config.from_env()

    # Esquema/migración de BD (incluye precision_on)
    asyncio.run(repo.ensure_schema(cfg.db_path))

    # Construir app
    setup_logging()
    app = build_app(cfg)

    # Política de loop estable en Windows (no molesta en otros SO)
    if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Ejecutar (bloqueante)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
