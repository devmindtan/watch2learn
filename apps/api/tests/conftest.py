import pytest


@pytest.fixture(autouse=True)
def laptop_only(monkeypatch):
    """Tests never reach the real GPU machine over SSH."""
    monkeypatch.setenv("WATCH2LEARN_GPU", "off")


@pytest.fixture(autouse=True)
def no_background_preparation(monkeypatch):
    """Completed test jobs do not start the background lesson writer."""
    from watch2learn import prepare

    monkeypatch.setattr(prepare, "enqueue", lambda lesson_id: None)
