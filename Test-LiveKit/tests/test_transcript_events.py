from transcript_events import TranscriptEventTracker


def test_user_interim_and_final_share_utterance_id_and_increment_seq():
    tracker = TranscriptEventTracker(session_id="room-a")
    e1 = tracker.on_user_transcribed(transcript="明日の", is_final=False, timestamp=1.0)
    e2 = tracker.on_user_transcribed(transcript="明日の天気", is_final=True, timestamp=2.0)

    assert e1 is not None and e2 is not None
    assert e1["session_id"] == "room-a"
    assert e1["utterance_id"] == e2["utterance_id"]
    assert e1["turn_id"] == "turn-1"
    assert e1["status"] == "interim"
    assert e2["status"] == "final"
    assert e2["seq"] == e1["seq"] + 1


def test_assistant_interrupted_distinguishes_spoken_and_generated_text():
    tracker = TranscriptEventTracker(session_id="room-a")
    tracker.on_user_transcribed(transcript="こんにちは", is_final=True, timestamp=1.0)
    ev = tracker.on_conversation_item_added(
        role="assistant",
        text="こんにちは、何か",
        generated_text="こんにちは、何かお手伝いしましょうか。",
        interrupted=True,
        timestamp=2.0,
    )

    assert ev is not None
    assert ev["status"] == "interrupted"
    assert ev["spoken_text"] == "こんにちは、何か"
    assert ev["generated_text"] == "こんにちは、何かお手伝いしましょうか。"


def test_status_event_uses_shared_schema():
    tracker = TranscriptEventTracker(session_id="room-a")
    ev = tracker.make_status_event(
        kind="memory",
        status="running",
        execution_id="exec-1",
        label="記憶を確認中",
        timestamp=3.0,
    )
    assert ev["type"] == "agent_status_event"
    assert ev["session_id"] == "room-a"
    assert ev["execution_id"] == "exec-1"
    assert ev["kind"] == "memory"
    assert ev["status"] == "running"
