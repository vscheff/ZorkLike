"""Private preflight. Exercise the real handlers and saves using disposable runs."""

import re
import tempfile
from collections import deque
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import actions
import store
import world as w


class Play:
    def __init__(self, game):
        self.game = game

    @property
    def now(self):
        return self.game.context()["state"]

    def request(self, op, **fields):
        here = self.game.context()
        return {"profile": here["profile"], "run": here["run"], "revision": here["revision"],
                "request_id": uuid4().hex, "command": "PREFLIGHT",
                "action": {"op": op, **fields}}

    def do(self, op, **fields):
        result = self.game.turn(self.request(op, **fields))
        assert not result["refused"], (op, fields, result["text"], result["view"]["room"])
        return result

    def act(self, kind, **fields):
        return self.do("act", kind=kind, **fields)

    def walk(self, directions):
        for direction in directions.split():
            self.do("move", direction=direction)

    def take(self, *items):
        for item in items:
            self.do("take", item=item)

    def safe_window(self, length):
        tick = self.now["tick"]
        next_start = next(d for d in range(12)
                          if all(w.TIDE[(tick + d + n) % 12] < 2 for n in range(length + 1)))
        if next_start:
            self.do("wait", marks=next_start)

    def observe(self, fact, target=None, method="examine"):
        return self.do("observe", fact=fact, target=target, method=method)


def check_world():
    described = set()
    for region, rooms in w.WORLD["regions"].items():
        path = w.GAME / "regions" / f"{region}.md"
        ids = re.findall(r"^## .([a-z_]+).$", path.read_text(encoding="utf-8"), re.MULTILINE)
        assert len(ids) == len(rooms) and set(ids) == rooms.keys()
        assert not described.intersection(ids)
        described.update(ids)
    queue = deque(["vestibule"])
    accessible = set()
    while queue:
        room = queue.popleft()
        if room in accessible:
            continue
        accessible.add(room)
        queue.extend(dest for dest, _ in w.EXITS[room].values())
    assert accessible == described == w.ROOMS.keys()
    assert set(w.DARK) | set(w.WASH) | w.UNDER_RISK <= accessible
    assert all(row["at"] in accessible for row in w.FIXTURES.values())
    for person in w.PEOPLE.values():
        cycle = person["route"]
        assert all(a == b or (b, None) in w.EXITS[a].values()
                   for a, b in zip(cycle, cycle[1:] + cycle[:1]))
    assert all(b in {dest for dest, _ in w.EXITS[a].values()} for a, b in w.MERA_EVACUATION.items())
    s = store.baseline()
    assert w.tide(s) == 0 and s["tick"] == 0 and len(s["events"]) == 0
    assert w.view(s)["objects"] == {"lamp": "tin lamp"}
    assert not w.completed(s)


def reach_east(play):
    play.take("lamp")
    play.walk("w")
    play.take("oil_tin", "counterweight", "shim")
    play.walk("e n")
    play.do("place", item="counterweight", target="hatch_pan")
    play.do("place", item="shim", target="hatch_taper")
    play.take("counterweight")
    play.do("drop", item="counterweight")
    play.walk("d")
    play.do("lamp", setting="light")
    play.walk("ne")
    play.take("rigging")
    play.do("place", item="rigging", target="drive_socket")
    play.walk("sw d")
    play.act("call_cradle", setting="down")
    play.do("wait", marks=3, until="cradle")
    assert play.now["cradle"]["position"] == "down"
    play.walk("d e n n")
    play.do("wait", marks=5, until="person", person="mera")
    play.do("talk", person="mera", topic="slip")
    assert w.carried(play.now, "witness_strip")
    play.walk("n")
    play.act("open_root")
    play.walk("u u")
    if play.now["lamp"]["lit"]:
        play.do("lamp", setting="snuff")
    play.walk("n")
    play.take("seed_box")
    play.walk("s e n")
    play.do("drop", item="seed_box")
    play.walk("s e s")
    play.take("packing_cord")
    play.walk("s")
    play.do("place", item="packing_cord", target="east_packing")
    play.act("east_valve", setting="open")
    play.walk("w")
    play.do("wait", marks=12, until="east_full")
    play.act("east_seat")
    assert w.bed_ready(play.now, "east")
    play.walk("n e")


def reach_west(play):
    play.take("lamp")
    play.walk("w")
    play.take("oil_tin")
    play.walk("e s e e s")
    play.safe_window(3)
    play.walk("e")
    assert "d" not in w.view(play.now)["exits"]
    play.observe("inlet_eye", "inlet_eye", "search")
    play.act("open_inlet", item="belt_hook")
    play.walk("d")
    play.do("lamp", setting="light")
    play.walk("s e n e")
    play.act("open_foil")
    play.take("spare_foil")
    play.walk("n e")
    play.act("press_foil")
    play.walk("s")
    play.observe("pier_mark")
    play.walk("w w n n")
    play.act("open_root")
    play.walk("u u")
    if play.now["lamp"]["lit"]:
        play.do("lamp", setting="snuff")
    play.do("lamp", setting="refill")


def file_intake(play, witness, test_bad_trace=False):
    play.walk("e e e e e n e n n e n")
    play.observe("loop_overlay", "loop_chart", "read")
    play.walk("s e")
    play.take("recorder_leaf")
    play.walk("w w s s w s s e e e e n")
    play.do("place", item="recorder_leaf", target="scratch_frame")
    play.act("recorder_loop", setting=19)
    if test_bad_trace:
        play.do("wait", marks=12, until="high")
        play.act("draw")
        play.do("wait", marks=3, until="draw")
        assert play.now["objects"]["recorder_leaf"]["reading"] == "blurred"
    play.safe_window(3)
    play.act("draw")
    play.do("wait", marks=3, until="draw")
    play.take("recorder_leaf")
    assert play.now["objects"]["recorder_leaf"]["reading"] == "trace19"
    assert "recorder_leaf:trace19" not in play.now["knowledge"]["facts"]
    play.do("observe", method="read", target="recorder_leaf")
    assert "recorder_leaf:trace19" in play.now["knowledge"]["facts"]
    play.walk("s w w w n w w n n w")
    play.act("file_claim", item=witness)
    play.take("writ")


def finish_west_bed(play):
    play.walk("e n n w")
    play.take("shoe")
    play.walk("s w w n w s s e")
    play.do("place", item="shoe", target="west_socket")
    play.act("west_vent", setting="river")
    play.do("wait", marks=12, until="low")
    play.act("west_test")
    assert w.bed_ready(play.now, "west")
    play.do("wait", marks=6, until="person", person="iss")
    play.do("warn", person="iss")
    play.walk("w n n e n")


def close_claim(play, bed):
    play.act("admit_writ")
    play.walk("n n")
    play.act("select", loop=19, bed=bed)
    play.walk("n")
    if bed == "east":
        # Two alternatives from the same actual state, with independent clocks.
        saved = play.now
        delay = (1 - saved["tick"]) % 12
        if delay:
            saved, _ = actions.resolve(saved, {"op": "wait", "marks": delay})
        running, _ = actions.resolve(saved, {"op": "act", "kind": "engage"})
        stopped, _ = actions.resolve(running, {"op": "act", "kind": "stop"})
        assert stopped["transfer"]["stage"] == "idle" and stopped["transfer"]["old_link"]
        failed, _ = actions.resolve(running, {"op": "wait", "marks": 2})
        assert failed["actor"]["status"] == "playing" and failed["transfer"]["collapsed"]
        assert not w.completed(failed) and not failed["filing"]["returned"]

    play.safe_window(3)
    play.act("engage")
    draw = play.do("wait", marks=3, until="transfer")
    assert draw["view"]["gauges"]["works"] == "complete"
    assert play.now["actor"]["status"] == "playing"
    play.take("closing_band")
    play.walk("s se w s e s e s s w s w w n s w")
    if play.now["lamp"]["fuel"] < 8:
        play.do("lamp", setting="refill")
    play.do("lamp", setting="light")
    play.walk("d d s s e")
    assert not w.completed(play.now)
    outcome = play.act("post_return")
    assert outcome["view"]["status"] == "complete" and outcome["ending"]["bed"] == bed
    assert outcome["ending"]["seed_stock"] == ("on_roof" if bed == "east" else "viable")
    assert outcome["ending"]["warned"] == (bed == "west")
    blocked = play.game.turn(play.request("move", direction="n"))
    assert blocked["refused"] and blocked["elapsed"] == 0


def check_runs(game):
    game.initialize()
    play = Play(game)
    reach_east(play)
    file_intake(play, "witness_strip")
    play.walk("n w n n")
    close_claim(play, "east")
    east = game.context()
    archived = game.paths(east["profile"], east["run"])
    original_bytes = [file.read_bytes() for file in archived]

    create = {**game.reference(east), "request_id": uuid4().hex, "name": "Second runner"}
    game.new_run("new-player", create)
    assert game.context()["state"] == store.baseline()
    assert game.new_run("new-player", create)["replay"]
    reach_west(play)
    file_intake(play, "spare_foil", test_bad_trace=True)
    finish_west_bed(play)
    close_claim(play, "west")
    west = game.context()
    assert east["run"] != west["run"] and east["profile"] != west["profile"]
    assert [file.read_bytes() for file in archived] == original_bytes
    game.switch({"name": "Runner"})
    assert game.context()["state"] == east["state"]
    try:
        game.new_run("new-player", create)
    except store.RequestError:
        pass
    else:
        raise AssertionError("An old request created another profile after a switch")
    assert len(game.profiles()) == 2
    game.switch({"name": "Second runner"})
    assert game.context()["state"] == west["state"]

    reset = {**game.reference(west), "request_id": uuid4().hex}
    try:
        game.new_run("confirm-reset", reset)
    except store.RequestError:
        pass
    else:
        raise AssertionError("Reset ran without an explicit pending request")
    game.reset_request(reset)
    assert game.context()["reset_requested"]
    game.new_run("confirm-reset", reset)
    assert game.context()["state"] == store.baseline()
    assert game.index()["profiles"][west["profile"]]["archives"] == [west["run"]]
    west_state, west_journal = game.paths(west["profile"], west["run"])
    assert store.read_json(west_state)["state"] == west["state"] and west_journal.is_file()
    assert [file.read_bytes() for file in archived] == original_bytes
    assert store.baseline()["tick"] == 0


def check_failures(game):
    game.initialize()
    play = Play(game)
    play.take("lamp")
    play.walk("s s")
    washed = play.do("wait", marks=6)
    assert washed["elapsed"] == 1 and washed["view"]["room"] == "sill_walk"
    assert play.now["objects"]["lamp"]["condition"] == "ruined" and play.now["actor"]["health"] == 2
    play.do("wait")
    dead = play.do("move", direction="s", force=True)
    assert dead["view"]["status"] == "dead"
    before = game.context()
    request = {**game.reference(before), "request_id": uuid4().hex}
    game.new_run("new-game", request)
    assert game.context()["state"] == store.baseline()
    assert game.index()["profiles"][before["profile"]]["archives"] == [before["run"]]

    # Never archive a different state under a stale reset confirmation.
    game.reset_request(game.reference(game.context()))
    play.do("wait")
    try:
        game.new_run("confirm-reset", {**game.reference(game.context()), "request_id": uuid4().hex})
    except store.RequestError:
        pass
    else:
        raise AssertionError("Stale reset confirmation was accepted")

    play.walk("u")
    play.observe("loft_gap", "loft_panel", "search")
    play.act("get_loft", item="belt_hook")
    play.take("ferry_key")
    play.act("open_loft", item="belt_hook")
    play.walk("e w d w w")
    play.act("open_ferry")
    play.take("ferry_list", "old_counter")
    play.walk("e e n e e n n")
    play.do("publish", item="ferry_list")
    assert play.now["rent_posted"] == "ferry_list"


def check_recovery(root):
    game = store.Store(root)
    with game.session():
        game.initialize()
        play = Play(game)
        request = play.request("take", item="lamp")
        # Leave a prepared transaction and deliberately append an incomplete line.
        recover = game.recover
        game.recover = lambda: None
        try:
            game.turn(request)
        finally:
            game.recover = recover
        pending = store.read_json(game.pending)
        path, journal = game.paths(request["profile"], request["run"])
        assert store.read_json(path)["revision"] == 0
        line = store.encoded(pending["entry"]) + b"\n"
        with journal.open("ab") as stream:
            stream.write(line[:len(line) // 2])

    with store.Store(root).session() as reopened:
        context = reopened.context()
        assert context["revision"] == 1 and w.carried(context["state"], "lamp")
        assert reopened.turn(request)["replay"]
        assert len(journal.read_bytes().splitlines()) == 2
        proposal = {**request, "request_id": uuid4().hex}
        try:
            reopened.turn(proposal)
        except store.RequestError:
            pass
        else:
            raise AssertionError("Stale turn accepted")
        assert reopened.context()["state"]["tick"] == 1

        # Replay the interrupted-clear case with a complete line and state.
        store.atomic_json(reopened.pending, pending)
        reopened.recover()
        assert not reopened.pending.exists() and len(journal.read_bytes().splitlines()) == 2
        assert reopened.context()["state"] == context["state"]


def main():
    check_world()
    with tempfile.TemporaryDirectory(prefix=".preflight-", dir=store.ROOT) as name:
        root = Path(name).resolve()
        assert root.parent == store.ROOT.resolve() and root.name.startswith(".preflight-")
        with store.Store(root / "runs").session() as game:
            check_runs(game)
        with store.Store(root / "failures").session() as game:
            check_failures(game)
        check_recovery(root / "recovery")
    print(f"Preflight passed. {len(w.ROOMS)} rooms, {len(w.PEOPLE)} schedules, two completed runs.")
    print("Also checked discovery, optional evidence, failure, archive fidelity, isolation and interrupted saves.")


if __name__ == "__main__":
    main()
