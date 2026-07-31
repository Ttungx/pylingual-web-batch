from pylingual_web_batch.queue import QueueGate


def test_queue_gate_closes_at_limit_and_logs_once():
    messages = []
    gate = QueueGate(10, logger=messages.append)
    assert gate.before_upload() is True
    gate.observe_upload(9)
    assert gate.before_upload() is True
    gate.observe_upload(10)
    assert gate.before_upload() is False
    assert gate.before_upload() is False
    assert len(messages) == 1


def test_queue_gate_ignores_unknown_position():
    gate = QueueGate(10, logger=lambda _: None)
    gate.observe_upload(None)
    assert gate.allowed is True
