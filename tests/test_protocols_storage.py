from netconfig.protocols import available_protocols


def test_cli_is_implemented_structured_protocols_are_explicit_future_adapters():
    caps = available_protocols()
    assert caps["cli_ssh"].implemented is True
    assert caps["cli_ssh"].structured is False
    assert caps["netconf"].structured is True
    assert caps["restconf"].structured is True
    assert caps["gnmi"].structured is True
