"""CPU-only publication race check; does not exercise native SDK resources."""
import copy
import threading


def test_status_copies_state_and_frame_in_one_generation(monkeypatch):
    from renderer import service

    old_motion = {"coaster_phase": 0.1, "wheel_angle": 0.2}
    new_motion = {"coaster_phase": 0.8, "wheel_angle": 0.9}
    copied, attempted, finished = threading.Event(), threading.Event(), threading.Event()
    metadata = {"frame": 1, "accepted_state_revision": "old-revision"}
    monkeypatch.setattr(service, "state", {"ready": True, "frame": 1, "ride_motion": old_motion})

    class InterleavingCache:
        def read(self):
            # status has already copied service.state. A writer attempts to publish
            # a new generation exactly before frame metadata is read.
            copied.set()
            assert attempted.wait(2)
            assert not finished.wait(0.03), "Publisher escaped status's generation lock"
            return b"image", copy.deepcopy(metadata)

    monkeypatch.setattr(service, "frames_cache", InterleavingCache())

    def publish_next_generation():
        assert copied.wait(2)
        attempted.set()
        with service.lock:
            service.state.update(frame=2, ride_motion=new_motion)
            metadata.update(frame=2, accepted_state_revision="new-revision")
        finished.set()

    publisher = threading.Thread(target=publish_next_generation)
    publisher.start()
    try:
        result = service.status()
    finally:
        publisher.join(2)
    assert not publisher.is_alive()
    assert finished.is_set()
    assert result["frame"] == 1
    assert result["accepted_state_revision"] == "old-revision"
    assert result["ride_motion"] == old_motion
