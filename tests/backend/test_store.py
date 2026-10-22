# -*- coding: utf-8 -*-
from src.backend.app.store.sqlite import InvestigationStore


def test_event_seq_and_replay(tmp_store: InvestigationStore):
    snap = tmp_store.create("PO-01332 三单是否匹配？", True)
    e1 = tmp_store.append_event(snap.id, "status.changed", {"status": "routing"})
    e2 = tmp_store.append_event(snap.id, "route.decided", {"mode": "single"})
    assert e1["seq"] == 1
    assert e2["seq"] == 2
    replay = tmp_store.events_after(snap.id, 1)
    assert [e["seq"] for e in replay] == [2]
    loaded = tmp_store.get(snap.id)
    assert loaded.eventSeq == 2
    assert loaded.wantReport is True


def test_cancel_flag(tmp_store: InvestigationStore):
    snap = tmp_store.create("帮我查一下风险", False)

    def mutate(item):
        item.cancelled = True
        item.status = "cancelled"

    tmp_store.update(snap.id, mutate)
    assert tmp_store.get(snap.id).status == "cancelled"