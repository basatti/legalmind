from foundation import hello


def test_hello() -> None:
    """The example module should return the expected greeting."""
    assert hello() == "Hello from backend"
