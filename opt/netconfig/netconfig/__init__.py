"""netconfig -- zero-dependency network configuration manager."""
from pathlib import Path
import re

__version__ = "2.0.0"


def _installed_package_version():
    try:
        version = Path(__file__).with_name("PACKAGE_VERSION").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return __version__
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*-[0-9]+(?:\.[A-Za-z0-9_]+)*", version):
        return version
    return __version__


__package_version__ = _installed_package_version()
