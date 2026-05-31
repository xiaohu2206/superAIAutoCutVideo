from modules.task_progress_store import TaskProgressStore


def test_late_progress_payload_does_not_revive_completed_task():
    store = TaskProgressStore()
    store.update_from_payload(
        {
            "scope": "extract_subtitle",
            "project_id": "project-1",
            "task_id": "subtitle-task-1",
            "type": "completed",
            "phase": "done",
            "message": "subtitle extracted",
            "progress": 100,
        }
    )

    store.update_from_payload(
        {
            "scope": "extract_subtitle",
            "project_id": "project-1",
            "task_id": "subtitle-task-1",
            "type": "progress",
            "phase": "funasr_progress",
            "message": "FunASR: recognition done",
            "progress": 95,
        }
    )

    state = store.get_state("extract_subtitle", "project-1", "subtitle-task-1")
    assert state is not None
    assert state["status"] == "completed"
    assert state["type"] == "completed"
    assert state["progress"] == 100
    assert state["phase"] == "done"


def test_progress_payload_still_updates_running_task():
    store = TaskProgressStore()
    store.update_from_payload(
        {
            "scope": "extract_subtitle",
            "project_id": "project-1",
            "task_id": "subtitle-task-1",
            "type": "progress",
            "phase": "funasr_progress",
            "message": "FunASR: recognition done",
            "progress": 95,
        }
    )

    state = store.get_state("extract_subtitle", "project-1", "subtitle-task-1")
    assert state is not None
    assert state["status"] == "running"
    assert state["progress"] == 95
