"""Current source package identity for release regression assertions."""
from pathlib import Path
import re


def rpm_fields(spec=None):
    if spec is None:
        path = Path(__file__).resolve().parents[1] / "packaging/netconfig.spec"
        spec = path.read_text(encoding="utf-8")
    version = re.search(r"(?m)^Version:\s*(\S+)", spec).group(1)
    release = re.search(r"(?m)^Release:\s*(\S+)", spec).group(1).removesuffix("%{?dist}")
    return version, release
