from watch2learn import app as app_module
from watch2learn import jobs


def test_processing_job_retains_paths_for_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "DB_PATH", tmp_path / "watch2learn.sqlite3")
    work_dir = tmp_path / "jobs" / "lesson-active"
    source = work_dir / "source.mp4"
    work_dir.mkdir(parents=True)
    source.write_bytes(b"media")
    job = jobs.create("fingerprint", "lesson.mp4", work_dir, source, None)

    jobs.update(job["id"], "transcribing-mandarin", 50)

    assert jobs.pending() == [
        {
            "id": job["id"],
            "filename": "lesson.mp4",
            "work_dir": str(work_dir),
            "source_path": str(source),
            "subtitle_path": None,
        }
    ]


def test_startup_removes_only_abandoned_job_directories(monkeypatch, tmp_path):
    jobs_root = tmp_path / "jobs"
    abandoned = jobs_root / "lesson-abandoned"
    unrelated = jobs_root / "keep-me"
    abandoned.mkdir(parents=True)
    unrelated.mkdir()
    (abandoned / "source.mp4").write_bytes(b"temporary media")
    monkeypatch.setattr(app_module, "JOBS_ROOT", jobs_root)
    monkeypatch.setattr(jobs, "DB_PATH", tmp_path / "watch2learn.sqlite3")

    app_module.cleanup_abandoned_job_files()

    assert not abandoned.exists()
    assert unrelated.is_dir()


def test_startup_resumes_job_when_source_media_still_exists(monkeypatch, tmp_path):
    jobs_root = tmp_path / "jobs"
    work_dir = jobs_root / "lesson-resumable"
    source = work_dir / "source.mp4"
    work_dir.mkdir(parents=True)
    source.write_bytes(b"media")
    monkeypatch.setattr(app_module, "JOBS_ROOT", jobs_root)
    monkeypatch.setattr(jobs, "DB_PATH", tmp_path / "watch2learn.sqlite3")
    job = jobs.create("fingerprint", "lesson.mp4", work_dir, source, None)
    started = []
    monkeypatch.setattr(app_module, "start_job", lambda *args: started.append(args))

    app_module.resume_pending_jobs()

    assert started == [(job["id"], "lesson.mp4", source, work_dir, None)]
