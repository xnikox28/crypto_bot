from __future__ import annotations
import os

def ensure_apscheduler_tz_compat() -> None:
    # Desactiva con APSCHED_TZ_CHECK=0 si ya controlaste el entorno.
    if os.getenv("APSCHED_TZ_CHECK", "1") not in {"1", "true", "True"}:
        return

    import importlib.metadata as m
    try:
        v = m.version("tzlocal")
    except Exception:
        raise RuntimeError('No se detectó tzlocal. Instala: tzlocal==2.1 y pytz')

    def _parse(ver: str):
        parts = []
        for p in ver.split("."):
            n = "".join(ch for ch in p if ch.isdigit())
            parts.append(int(n) if n else 0)
        return tuple(parts)

    if _parse(v) >= (3, 0, 0):
        raise RuntimeError(
            f"Detectado tzlocal {v}. APScheduler 3.x necesita pytz puro.\n"
            "Ejecuta: pip uninstall -y tzlocal && pip install tzlocal==2.1 pytz"
        )

    from tzlocal import get_localzone
    from pytz.tzinfo import BaseTzInfo
    tz = get_localzone()
    if not isinstance(tz, BaseTzInfo):
        raise RuntimeError(
            "La zona local no es pytz. Ejecuta:\n"
            "  pip uninstall -y tzlocal\n"
            "  pip install tzlocal==2.1 pytz"
        )
