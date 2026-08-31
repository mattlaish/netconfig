"""Protocol capability registry.

CLI/OpenSSH remains the implemented fallback. Structured protocols are explicit
capabilities so NETCONF/RESTCONF/gNMI adapters can be added without coupling
business logic to screen-scraping.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolCapability:
    name: str
    structured: bool
    implemented: bool


CAPABILITIES = {
    "cli_ssh": ProtocolCapability("cli_ssh", structured=False, implemented=True),
    "netconf": ProtocolCapability("netconf", structured=True, implemented=False),
    "restconf": ProtocolCapability("restconf", structured=True, implemented=False),
    "gnmi": ProtocolCapability("gnmi", structured=True, implemented=False),
}


def available_protocols():
    return dict(CAPABILITIES)
