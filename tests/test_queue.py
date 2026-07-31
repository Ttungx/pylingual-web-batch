from pylingual_web_batch.queue import QueueGate


def test_queue_gate_closes_at_limit_and_logs_once():
    messages = []
    gate = QueueGate(10, logger=messages.append)
    first = gate.reserve_upload()
    assert first is not None
    first.observe(9)
    second = gate.reserve_upload()
    assert second is not None
    second.observe(10)
    assert gate.reserve_upload() is None
    assert gate.reserve_upload() is None
    assert len(messages) == 1


def test_queue_gate_ignores_unknown_position():
    gate = QueueGate(10, logger=lambda _: None)
    reservation = gate.reserve_upload()
    assert reservation is not None
    reservation.observe(None)
    assert gate.allowed is True


def test_queue_gate_allows_only_one_unobserved_upload():
    gate = QueueGate(1, logger=lambda _: None)

    reservation = gate.reserve_upload()

    assert reservation is not None
    assert gate.reserve_upload() is None
    reservation.observe(0)
    assert gate.reserve_upload() is not None


def test_queue_gate_release_after_failed_upload_allows_next():
    gate = QueueGate(1, logger=lambda _: None)
    reservation = gate.reserve_upload()
    assert reservation is not None

    reservation.release()

    assert gate.reserve_upload() is not None
