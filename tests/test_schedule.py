"""The generated auto-sync script: rendering and health-check contracts."""


def test_sync_script_carries_cron_doctor_check():
    import schedule
    script = schedule._SCRIPT_TEMPLATE.format(
        plugin_root="/tmp/p", settings_path="/tmp/s.json")
    compile(script, "gen.py", "exec")
    assert '"cron", "doctor"' in script  # subprocess argv
    assert "SCHEDULED JOBS WARNING" in script
    assert 'prev["cronDoctor"]' in script
    # exit 1 warns; other exits stay silent (older hermes without doctor)
    assert "returncode == 1" in script
    assert '{"skipped": "unavailable"}' in script


def test_sync_script_warn_latches():
    import schedule
    script = schedule._SCRIPT_TEMPLATE.format(
        plugin_root="/tmp/p", settings_path="/tmp/s.json")
    compile(script, "gen.py", "exec")
    # settings load once, before either latch reads it
    assert script.count("settings_path = Path") == 1
    assert script.index("prev = json.loads") < script.index('memoryWarnAt')
    # both warnings latch for 24h and persist their timestamps
    assert 'prev.get("memoryWarnAt", 0) > 24 * 3600' in script
    assert 'prev["memoryWarnAt"]' in script
    assert 'prev.get("cronDoctorWarnAt", 0) > 24 * 3600' in script
    assert 'prev["cronDoctorWarnAt"]' in script


def test_sync_job_delivers_to_origin(monkeypatch, tmp_path):
    """Health warnings must be able to reach chat: origin -> home channel -> local."""
    import schedule
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    created, updated = {}, {}
    class FakeJobs:
        def resolve_job_ref(self, ref): return None if not created else created
        def create_job(self, **kw):
            created.update(kw); created["id"] = "j1"; return created
        def update_job(self, jid, patch): updated.update(patch)
        def remove_job(self, jid): pass
    monkeypatch.setitem(__import__("sys").modules, "cron", type("m", (), {"jobs": FakeJobs()})())
    monkeypatch.setitem(__import__("sys").modules, "cron.jobs", FakeJobs())
    schedule.ensure_sync_job(tz_offset_minutes=240)
    assert created["deliver"] == "origin"
    schedule.ensure_sync_job(tz_offset_minutes=240)
    assert updated.get("deliver") == "origin"
