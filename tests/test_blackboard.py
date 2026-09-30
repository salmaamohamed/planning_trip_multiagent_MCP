import threading

import pytest

from app.blackboard import Blackboard, BlackboardKeys


def test_write_then_read():
    bb = Blackboard("s1")
    bb.write(BlackboardKeys.FLIGHTS, {"status": "ok", "options": [{"airline": "X"}]}, author="flight_agent")
    assert bb.read(BlackboardKeys.FLIGHTS)["options"][0]["airline"] == "X"
    assert bb.entry(BlackboardKeys.FLIGHTS).written_by == "flight_agent"
    assert bb.session_id == "s1"


def test_read_missing_returns_default():
    bb = Blackboard()
    assert bb.read("nope") is None
    assert bb.read("nope", default=[]) == []
    assert not bb.has("nope")


def test_read_returns_copy_so_readers_cannot_mutate_shared_data():
    bb = Blackboard()
    bb.write("hotels", {"options": [{"name": "A"}]})
    snapshot = bb.read("hotels")
    snapshot["options"].append({"name": "INJECTED"})
    assert bb.read("hotels") == {"options": [{"name": "A"}]}


def test_write_copies_input():
    bb = Blackboard()
    value = {"options": []}
    bb.write("k", value)
    value["options"].append(1)
    assert bb.read("k") == {"options": []}


def test_update_merges_dicts_and_bumps_version():
    bb = Blackboard()
    bb.write("trip_constraints", {"destination": "Paris", "budget": None})
    bb.update("trip_constraints", {"budget": 1500}, author="planner_agent")
    assert bb.read("trip_constraints") == {"destination": "Paris", "budget": 1500}
    assert bb.entry("trip_constraints").version == 2


def test_update_replaces_non_dict_values():
    bb = Blackboard()
    bb.write("k", [1, 2])
    bb.update("k", [3])
    assert bb.read("k") == [3]


def test_update_missing_key_raises():
    with pytest.raises(KeyError):
        Blackboard().update("missing", {})


def test_get_all_returns_every_key():
    bb = Blackboard()
    for key in BlackboardKeys.SPECIALIST_KEYS:
        bb.write(key, {"status": "ok"})
    assert set(bb.get_all()) == set(BlackboardKeys.SPECIALIST_KEYS)


def test_sessions_are_isolated():
    a, b = Blackboard(), Blackboard()
    a.write("flights", {"status": "ok"})
    assert b.read("flights") is None
    assert a.session_id != b.session_id


def test_concurrent_updates_are_not_lost():
    bb = Blackboard()
    bb.write("counter", {})

    def worker(i):
        for j in range(50):
            bb.update("counter", {f"{i}-{j}": True})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(bb.read("counter")) == 8 * 50
