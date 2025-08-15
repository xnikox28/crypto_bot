from __future__ import annotations
import warnings

def silence_pkg_resources_warning() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r"pkg_resources is deprecated as an API",
        category=UserWarning,
    )
