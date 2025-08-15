# bot/handlers/error.py
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import (
    NetworkError, TimedOut, RetryAfter, Conflict, BadRequest
)

logger = logging.getLogger("crypto-bot")

TRANSIENT = (NetworkError, TimedOut, RetryAfter)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Manejador global de errores:
    - Ignora 'message is not modified' (y variantes).
    - Trata timeouts/red como transitorios.
    - Maneja Conflict (doble instancia) sin tumbar el proceso.
    - Silencia 'file must be non-empty' (ya que reenviamos con buffer fresco).
    - Loguea el resto con stacktrace.
    """
    err = context.error
    err_str = (str(err).lower() if err is not None else "")

    # Inofensivos al editar/reenviar
    if isinstance(err, BadRequest) and any(s in err_str for s in [
        "message is not modified",
        "message content is not modified",
        "file must be non-empty",
        "can't parse inputmedia",
        "media not found",
        "message to edit not found",
        "message can't be edited",
        "replied message not found",
    ]):
        logger.info("BadRequest no crítica: %s", err)
        return

    # Transitorios
    if isinstance(err, TRANSIENT):
        logger.warning("Transitorio Telegram (ignorado): %r", err)
        return

    # Doble instancia
    if isinstance(err, Conflict):
        logger.error("Otra instancia está ejecutándose (Conflict). Cierra una de ellas.")
        try:
            if isinstance(update, Update) and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ Se detectó otra instancia del bot (Conflict)."
                )
        except Exception:
            pass
        return

    # Cualquier otro error
    logger.exception("Excepción no manejada", exc_info=err)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Ocurrió un error inesperado. Se registró en los logs."
            )
    except Exception:
        pass

