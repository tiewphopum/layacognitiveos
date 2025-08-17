# tests/test_semantic_memory.py
# -*- coding: utf-8 -*-
import time
from pathlib import Path
import pytest

from layaos.cognition.semantic import SemanticMemory


@pytest.fixture()
def sem(tmp_path: Path):
    db = str(tmp_path / "sem.sqlite")
    s = SemanticMemory(db_path=db)
    yield s
    s.close()


def test_add_and_get(sem: SemanticMemory):
    sem.add(("camera", {"vendor": "Axis", "model": "P3245"}))
    d = sem.get("camera")
    assert d and d["vendor"] == "Axis"
    assert sem.get_object_details("camera") == d


def test_learn_overwrite(sem: SemanticMemory):
    sem.learn_object("pipeline", {"stages": ["s1", "s2"]})
    sem.learn_object("pipeline", {"stages": ["s1", "s2", "s3"]})
    d = sem.get("pipeline")
    assert d and d["stages"][-1] == "s3"


def test_exists_and_remove(sem: SemanticMemory):
    sem.learn_object("mq", {"type": "RabbitMQ"})
    assert sem.exists("mq") is True
    ok = sem.remove("mq")
    assert ok is True
    assert sem.get("mq") is None


def test_list_and_search(sem: SemanticMemory):
    sem.learn_object("motion", {"desc": "detect motion in 3x3 grid"})
    sem.learn_object("tracker", {"desc": "track objects across frames"})
    sem.learn_object("bus", {"desc": "RabbitMQ event bus"})

    names = sem.list_names(limit=10)
    assert "motion" in names and "tracker" in names

    res = sem.search("bus")
    keys = {r["name"] for r in res}
    assert "bus" in keys
