import os
import time

from chemlab.evidence.bounded import dependency_call, dependency_session


def delayed_result(seconds):
    time.sleep(seconds)
    return {"status": "pass", "pid": os.getpid()}


def abrupt_worker_exit():
    os._exit(7)


def test_dependency_deadline_interrupts_worker_and_next_operation_recovers():
    with dependency_session():
        before = dependency_call(delayed_result, (0,))
        result = dependency_call(delayed_result, (3,), timeout=0.1)
        assert result == {
            "status": "error",
            "reason": "dependency_operation_timeout",
            "timeout_seconds": 0.1,
        }
        after = dependency_call(delayed_result, (0,))
    assert before["status"] == after["status"] == "pass"
    assert before["pid"] != after["pid"]


def test_crashed_worker_is_error_and_cannot_poison_following_checks():
    with dependency_session():
        result = dependency_call(abrupt_worker_exit, ())
        assert result["status"] == "error"
        assert result["reason"] == "dependency_worker_error"
        assert dependency_call(delayed_result, (0,))["status"] == "pass"
