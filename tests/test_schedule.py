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
