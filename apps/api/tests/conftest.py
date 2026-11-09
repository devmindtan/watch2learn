import pytest


@pytest.fixture(autouse=True)
def laptop_only(monkeypatch):
    """Tests never reach the real GPU machine over SSH."""
    monkeypatch.setenv("WATCH2LEARN_GPU", "off")
