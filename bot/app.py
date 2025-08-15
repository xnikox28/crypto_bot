from __future__ import annotations
from telegram.ext import Application, ApplicationBuilder, CommandHandler, AIORateLimiter, CallbackQueryHandler

from .config import Config

# Mantengo tu import agregador para el resto de comandos:
from .handlers import (
    start_cmd, setcoin_cmd, setsymbol_cmd, estado_cmd,
    niveles_cmd, grafica_cmd, tp_cmd, sl_cmd, modo_cmd,
    alerts_cmd, config_cmd, purge_cmd, clearbot_cmd,
    clearchat_cmd, precision_cmd, header_cmd,
)

# 👇 Importo estos dos directamente de sus módulos para evitar errores de re-export:
from .handlers.commands.darkmode import darkmode_cmd
from .handlers.commands.commands import commands_cmd

from .handlers.commands.estado import estado_cb
from .handlers.commands.config import config_cb

from .handlers.error import error_handler




def build_app(cfg: Config) -> Application:
    app = (
        ApplicationBuilder()
        .token(cfg.token)
        .rate_limiter(AIORateLimiter())
        .build()
    )
    app.bot_data["config"] = cfg
    app.bot_data.setdefault("precision_chats", set())
    app.bot_data.setdefault("runtime", {})  # para cooldown/peaks/etc.

    # Comandos
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("setcoin", setcoin_cmd))
    app.add_handler(CommandHandler("setsymbol", setsymbol_cmd))
    app.add_handler(CommandHandler("niveles", niveles_cmd))
    app.add_handler(CommandHandler("grafica", grafica_cmd))
    app.add_handler(CommandHandler("tp", tp_cmd))
    app.add_handler(CommandHandler("sl", sl_cmd))
    app.add_handler(CommandHandler("modo", modo_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("commands", commands_cmd))
    app.add_handler(CommandHandler("header", header_cmd))

    #COMANDOS CON CALLBACKS INTEGRADOS
    app.add_handler(CallbackQueryHandler(estado_cb, pattern=r"^state:"))
    app.add_handler(CommandHandler("estado", estado_cmd))

    app.add_handler(CallbackQueryHandler(config_cb, pattern=r"^cfg:"))
    app.add_handler(CommandHandler("config", config_cmd))

    

    # Limpieza
    app.add_handler(CommandHandler("purge", purge_cmd))
    app.add_handler(CommandHandler("clearbot", clearbot_cmd))
    app.add_handler(CommandHandler("clearchat", clearchat_cmd))

    # Precisión
    app.add_handler(CommandHandler("precision", precision_cmd))

    # Modo oscuro global por chat
    app.add_handler(CommandHandler("darkmode", darkmode_cmd))

    # Manejador global de errores
    app.add_error_handler(error_handler)

    return app
