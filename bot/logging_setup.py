# bot/logging_setup.py
import logging, sys

def setup_logging(level=logging.INFO):
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # silenciar ruidosos
    for name in ("httpx", "httpcore", "telegram.request", "apscheduler"):
        logging.getLogger(name).setLevel(logging.WARNING)
