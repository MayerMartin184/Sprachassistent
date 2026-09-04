from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sprachassistent.presence import PresenceLogic
from sprachassistent.tools.memory import Memory
from sprachassistent.tools.reminders import Reminders


def test_memory_save_search_summary(tmp_path):
    m = Memory(tmp_path)
    a = m.save("Mit Herrn Schmidt vereinbart: Angebot bis Freitag", "absprache")
    m.save("Trinkt morgens Kaffee, keine Meetings vor 9", "gewohnheit")
    assert m.save("mit herrn schmidt vereinbart: angebot bis freitag")["id"] == a["id"]  # keine Dubletten
    assert [i["id"] for i in m.search("Schmidt")] == [a["id"]]
    assert "Gedächtnis" in m.summary() and "keine Meetings" in m.summary()
    assert m.forget(a["id"]) and not m.forget(999)


def test_reminders_due(tmp_path):
    tz = ZoneInfo("Europe/Berlin")
    r = Reminders(tmp_path, "Europe/Berlin")
    now = datetime(2026, 9, 4, 10, 0, tzinfo=tz)
    r.add("2026-09-04T09:55", "Rückruf Müller")
    later = r.add("2026-09-04T10:30", "Angebot abschicken")
    fired = r.due(now)
    assert [f["text"] for f in fired] == ["Rückruf Müller"]
    assert r.due(now) == []  # nicht doppelt
    assert [p["id"] for p in r.pending()] == [later["id"]]
    assert r.due(now + timedelta(hours=1))[0]["id"] == later["id"]


def test_presence_arrival_and_visitor():
    logic = PresenceLogic(absence_min=10, cooldown_min=0)
    t = 0.0
    # anwesend, dann 20 s weg -> abwesend
    for _ in range(3):
        assert logic.update(1, t) is None; t += 2.5
    for _ in range(8):
        logic.update(0, t); t += 2.5
    assert not logic.present
    # 11 Minuten später zurück -> Ankunft
    t += 11 * 60
    events = [logic.update(1, t + i * 2.5) for i in range(3)]
    assert events[-1] is not None and events[-1][0] == "arrival"
    t += 10
    # zweite Person zweimal innerhalb einer Stunde -> Störung beim zweiten Mal
    for _ in range(4):
        first = logic.update(2, t); t += 2.5
    assert first is None
    logic.update(1, t); t += 300
    second = None
    for _ in range(4):
        second = logic.update(2, t); t += 2.5
    assert second is not None and second[0] == "visitor"


def test_presence_cooldown_suppresses_repeat():
    logic = PresenceLogic(absence_min=0, cooldown_min=10)
    t = 0.0
    for _ in range(3):
        logic.update(1, t); t += 2.5
    for _ in range(8):
        logic.update(0, t); t += 2.5
    t += 1
    ev = [logic.update(1, t + i * 2.5) for i in range(3)]
    assert ev[-1] is not None
    # erneut weg und zurück innerhalb der Abkühlzeit -> kein zweites Ereignis
    t += 10
    for _ in range(8):
        logic.update(0, t); t += 2.5
    ev2 = [logic.update(1, t + i * 2.5) for i in range(3)]
    assert ev2[-1] is None
