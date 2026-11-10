"""Write every word and sentence lesson of a video ahead of time.

After an import (and at startup for saved videos) one background thread writes
the lessons of each video, so a click shows the lesson at once. Every word goes
into the global dictionary (word_dictionary.py) with its lesson; a word met in an
earlier video is never written again. The thread is resumable and idempotent:
anything already cached is skipped.

Machine rule: a multi-hour model run must not freeze the laptop, so preparation
runs only on the GPU machine (or an explicitly configured Ollama URL, or when
WATCH2LEARN_PREPARE_LOCAL=1). Without one it waits and checks again later; a
click still writes that one lesson on demand. While the learner uses speech
(TTS/ASR) on the shared 6 GB card it pauses and unloads the model.
"""

import logging
import os
import threading
import time

from . import explain, jobs, word_dictionary
from .gpu_host import GPU

logger = logging.getLogger(__name__)
WAIT_SECONDS = 300
SPEECH_QUIET_SECONDS = 120
MAX_FAILURES = 3

_lock = threading.Condition()
_queue: list[str] = []
_status: dict[str, dict] = {}
_thread: threading.Thread | None = None
_last_speech = 0.0


def note_speech() -> None:
    """Called when TTS/ASR runs, so preparation yields the GPU for a while."""
    global _last_speech
    _last_speech = time.monotonic()


def status(lesson_id: str) -> dict | None:
    with _lock:
        item = _status.get(lesson_id)
        return dict(item) if item else None


def enqueue(lesson_id: str) -> None:
    """Add the video's words to the dictionary now; write their lessons in the background."""
    global _thread
    job = jobs.get(lesson_id)
    if job and job["status"] == "complete":
        word_dictionary.register_lesson(lesson_id, job["result"].get("vocabulary", []))
    with _lock:
        if lesson_id not in _queue:
            _queue.append(lesson_id)
        _status.setdefault(lesson_id, {"state": "queued", "done": 0, "total": 0})
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="lesson-prepare", daemon=True)
            _thread.start()
        _lock.notify()


def model_url() -> str | None:
    """Where preparation may run the model, or None to wait (see module docstring)."""
    configured = os.environ.get("WATCH2LEARN_OLLAMA_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    url = GPU.endpoint("ollama")
    if url:
        return url
    if os.environ.get("WATCH2LEARN_PREPARE_LOCAL", "").lower() in {"1", "true", "yes"}:
        return explain.DEFAULT_URL
    return None


def _set(lesson_id: str, **fields) -> None:
    with _lock:
        _status.setdefault(lesson_id, {}).update(fields)


def _wait_for_model(lesson_id: str) -> str:
    unloaded_url = None
    while True:
        speaking = time.monotonic() - _last_speech < SPEECH_QUIET_SECONDS
        url = None if speaking else model_url()
        if url:
            return url
        if speaking:
            _set(lesson_id, state="paused", reason="đang nhường GPU cho giọng đọc")
            if unloaded_url is None and (current := GPU.endpoint("ollama", start=False)):
                explain.unload_model(current)
                unloaded_url = current
            time.sleep(15)
        else:
            _set(lesson_id, state="waiting", reason="chờ máy GPU bật")
            time.sleep(WAIT_SECONDS)


def prepare_lesson(lesson_id: str) -> None:
    job = jobs.get(lesson_id)
    if not job or job["status"] != "complete":
        return
    lesson = job["result"]
    word_dictionary.register_lesson(lesson_id, lesson.get("vocabulary", []))
    requests = explain.lesson_requests(lesson)
    missing = [item for item in requests if not explain.is_ready(item)]
    total = len(requests)
    _set(lesson_id, state="running", done=total - len(missing), total=total, reason=None)
    failures = 0
    for request in missing:
        if explain.is_ready(request):  # written by a click meanwhile
            _set(lesson_id, done=status(lesson_id)["done"] + 1)
            continue
        url = _wait_for_model(lesson_id)
        _set(lesson_id, state="running", reason=None)
        try:
            explain.write_lesson(request, url)
            failures = 0
        except Exception as error:  # one bad answer must not stop the video
            failures += 1
            logger.warning("Could not prepare lesson %s: %s", request.subject, error)
            if failures >= MAX_FAILURES:
                _set(lesson_id, state="error", reason=f"AI local lỗi: {error}")
                return
            continue
        _set(lesson_id, done=status(lesson_id)["done"] + 1)
    _set(lesson_id, state="complete", reason=None)


def _run() -> None:
    while True:
        with _lock:
            while not _queue:
                _lock.wait()
            lesson_id = _queue[0]
        try:
            prepare_lesson(lesson_id)
        except Exception as error:
            logger.warning("Lesson preparation of %s stopped: %s", lesson_id, error)
            _set(lesson_id, state="error", reason=str(error))
        finally:
            with _lock:
                _queue.remove(lesson_id)
