import pytest

from examples.deskmate_schedules import missed_reminder, interrupted


def test_exited_reminder_experiment(tmp_path):
    result = missed_reminder(tmp_path)
    assert result["model_calls"] == 0 and len(result["records"]) == 1


@pytest.mark.parametrize("stage", ["claimed", "written"])
def test_real_process_crash_and_reopen_experiment(tmp_path, stage):
    result = interrupted(tmp_path, stage)
    assert result["records"][0]["status"] == "interrupted"
    assert result["write_calls"] == (1 if stage == "written" else 0)
