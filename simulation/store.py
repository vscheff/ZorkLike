"""One-shot save operations for Codex. This module accepts structured actions only."""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import actions
import world

ROOT = Path(__file__).resolve().parents[1]
START = {"offset": 0, "start": 0, "digest": None}
PROFILE_ID = re.compile(r"player_[0-9]{3,8}")
RUN_ID = re.compile(r"[0-9a-f]{32}")
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,80}")


class SaveError(Exception):
    """Storage integrity failure. Report outside the fiction."""


class RequestError(Exception):
    """Invalid, stale or incomplete request. A reload may be enough."""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def state_digest(state):
    text = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return digest(text.encode("utf-8"))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path, value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".save-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def exclusive(path):
    if os.name == "nt":
        import msvcrt
    else:
        import fcntl

    with path.open("a+b") as lock:
        if os.name == "nt":
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            deadline = time.monotonic() + 8
            while True:
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RequestError("Another save operation still holds the project lock.")
                    time.sleep(0.05)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def baseline():
    source = (world.GAME / "INITIAL_STATE.json").read_bytes()
    expected = (world.GAME / "INITIAL_STATE.sha256").read_text(encoding="ascii").strip()
    if digest(source) != expected:
        raise SaveError("The immutable initial snapshot does not match its saved fingerprint.")
    state = json.loads(source)
    validate_state(state)
    return state


def validate_state(state):
    if state["version"] != world.WORLD["version"]:
        raise SaveError("The playthrough uses a different canon version.")
    actor = state["actor"]
    tick = state["tick"]
    if actor["room"] not in world.ROOMS or type(tick) is not int or tick < 0:
        raise SaveError("The current location or time is invalid.")
    if (type(actor["health"]) is not int or not 0 <= actor["health"] <= 3
            or actor["status"] not in {"playing", "dead", "complete"}
            or (actor["health"] == 0) != (actor["status"] == "dead")):
        raise SaveError("The runner's condition is invalid.")
    if set(state["objects"]) != set(world.OBJECTS) or set(state["people"]) != set(world.PEOPLE):
        raise SaveError("The saved objects or people differ from the canon.")
    positions = {*world.ROOMS, *world.HOLDERS, "carry", "gone", "cache_loft", "cache_ferry",
                 "cache_docket", "cache_foil", "with_mera", "unissued"}
    for obj in state["objects"].values():
        if obj["at"] not in positions or (obj["condition"] == "intact") == (obj["at"] == "gone"):
            raise SaveError("An object has an inconsistent position or condition.")
    if world.burden(state) > world.CAPACITY:
        raise SaveError("The saved inventory exceeds capacity.")
    for person, record in state["people"].items():
        if not 0 <= record["phase"] < len(world.PEOPLE[person]["route"]):
            raise SaveError("A resident has an invalid schedule position.")
    lamp = state["lamp"]
    if not 0 <= lamp["fuel"] <= 18 or not 0 <= lamp["reserve"] <= 24 or (lamp["lit"] and lamp["fuel"] == 0):
        raise SaveError("The lamp has an invalid oil measurement.")
    cradle = state["cradle"]
    if cradle["due"] is not None and (cradle["due"] <= tick or cradle["target"] not in {"up", "down"}):
        raise SaveError("The cradle schedule is incomplete.")
    scratch = state["scratch"]
    if scratch["due"] is not None and (scratch["due"] <= tick or not world.holder_has(state, "scratch_frame")):
        raise SaveError("A live draw has no seated leaf or deadline.")
    transfer = state["transfer"]
    if transfer["stage"] == "running" and not (0 < transfer["remaining"] <= 3 and transfer["old_link"]):
        raise SaveError("The running transfer has an invalid load state.")
    if transfer["stage"] == "complete" and (transfer["old_link"] or transfer["remaining"] != 0):
        raise SaveError("The completed transfer still carries its old stroke.")
    if actor["status"] == "complete":
        completed = deepcopy(state)
        completed["actor"]["status"] = "playing"
        if not world.completed(completed):
            raise SaveError("The closing record does not satisfy the saved conditions.")


def check_anchor(stream, anchor):
    if anchor == START:
        return b""
    start, stop = anchor["start"], anchor["offset"]
    if not 0 <= start < stop:
        raise SaveError("Invalid journal anchor.")
    stream.seek(start)
    line = stream.read(stop - start)
    if not line.endswith(b"\n") or digest(line) != anchor["digest"]:
        raise SaveError("The latest journal record does not match its saved anchor.")
    return line


def make_anchor(line, start):
    return {"start": start, "offset": start + len(line), "digest": digest(line)}


def tail(path, lines):
    """Read a bounded suffix of the active journal."""
    with path.open("rb") as stream:
        end = stream.seek(0, os.SEEK_END)
        stream.seek(max(0, end - 65536))
        raw = stream.read().splitlines()
    if end > 65536:
        raw = raw[1:]
    return [json.loads(entry) for entry in raw[-lines:]]


def request_id(request):
    key = request.get("request_id")
    if not isinstance(key, str) or not REQUEST_ID.fullmatch(key):
        raise RequestError("The request is missing a valid retry key.")
    return key


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.index_path = self.root / "INDEX.json"
        self.pending = self.root / "PENDING.json"

    @contextmanager
    def session(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with exclusive(self.root / ".save.lock"):
            self.recover()
            yield self

    def paths(self, profile, run):
        if not PROFILE_ID.fullmatch(profile) or not RUN_ID.fullmatch(run):
            raise SaveError("Invalid profile or playthrough identifier.")
        folder = self.root / profile / "runs" / run
        return folder / "STATE.json", folder / "JOURNAL.jsonl"

    def recover(self):
        if not self.pending.exists():
            return
        pending = read_json(self.pending)
        save, prior, entry = pending["save"], pending["prior"], pending["entry"]
        state_path, journal = self.paths(save["profile"], save["run"])
        state_path.parent.mkdir(parents=True, exist_ok=True)
        line = encoded(entry) + b"\n"
        if save["journal"] != make_anchor(line, prior["offset"]) or entry["state_digest"] != state_digest(save["state"]):
            raise SaveError("The interrupted transaction does not match its saved data.")
        if state_path.exists():
            current = read_json(state_path)
            if current != save and current["journal"] != prior:
                raise SaveError("A different save conflicts with the interrupted transaction.")
        elif prior != START:
            raise SaveError("An interrupted turn has lost its previous save.")
        with journal.open("a+b") as stream:
            check_anchor(stream, prior)
            stream.seek(prior["offset"])
            suffix = stream.read()
            if not line.startswith(suffix):
                raise SaveError("Unrecognized data follows the latest journal record.")
            stream.write(line[len(suffix):])
            stream.flush()
            os.fsync(stream.fileno())
        atomic_json(state_path, save)
        if pending["index"] is not None:
            atomic_json(self.index_path, pending["index"])
        self.pending.unlink()

    def commit(self, profile, run, state, prior, entry, index=None):
        validate_state(state)
        entry["state_digest"] = state_digest(state)
        line = encoded(entry) + b"\n"
        save = {"profile": profile, "run": run, "revision": entry["revision"], "state": state,
                "journal": make_anchor(line, prior["offset"])}
        atomic_json(self.pending, {"save": save, "prior": prior, "entry": entry, "index": index})
        self.recover()
        return save

    def index(self):
        if not self.index_path.exists():
            raise RequestError("There is no initialized playthrough.")
        index = read_json(self.index_path)
        if index["schema"] != 1 or index["active"] not in index["profiles"]:
            raise SaveError("The active profile index is invalid.")
        return index

    def load(self, index):
        profile = index["active"]
        run = index["profiles"][profile]["run"]
        state_path, journal = self.paths(profile, run)
        save = read_json(state_path)
        if (save["profile"], save["run"]) != (profile, run):
            raise SaveError("The active index points to a different playthrough.")
        with journal.open("rb") as stream:
            raw = check_anchor(stream, save["journal"])
            if not raw or stream.read(1):
                raise SaveError("The active journal has an incomplete or uncommitted suffix.")
        entry = json.loads(raw)
        if entry["revision"] != save["revision"] or entry["state_digest"] != state_digest(save["state"]):
            raise SaveError("The current save does not match its latest journal record.")
        validate_state(save["state"])
        return save, entry

    @staticmethod
    def reference(save):
        return {key: save[key] for key in ("profile", "run", "revision")}

    def expect(self, save, request):
        if self.reference(save) != {key: request.get(key) for key in ("profile", "run", "revision")}:
            raise RequestError("The active playthrough changed. Reload before interpreting another turn.")

    def context(self):
        index = self.index()
        save, _ = self.load(index)
        _, journal = self.paths(save["profile"], save["run"])
        recent = tail(journal, 3)
        return {**self.reference(save), "name": index["profiles"][save["profile"]]["name"],
                "state": save["state"], "view": world.view(save["state"]), "recent": recent,
                "reset_requested": index["reset"] == self.reference(save)}

    def status(self):
        index = self.index()
        save, _ = self.load(index)
        view = world.view(save["state"])
        return {"name": index["profiles"][save["profile"]]["name"], "marks": view["tick"],
                "location": view["title"], "health": view["health"], "status": view["status"]}

    def profiles(self):
        index = self.index()
        return [{"id": ident, "name": row["name"], "active": ident == index["active"]}
                for ident, row in index["profiles"].items()]

    def turn(self, request):
        key = request_id(request)
        index = self.index()
        save, latest = self.load(index)
        command = request.get("command")
        action = request.get("action")
        if not isinstance(command, str) or len(command) > 3000 or not isinstance(action, dict):
            raise RequestError("A turn must contain a bounded command and one structured action.")
        fingerprint = state_digest(request)
        if latest.get("request_id") == key:
            if latest["request_fingerprint"] != fingerprint:
                raise RequestError("That retry key belongs to a different request.")
            return {**self.reference(save), **latest["outcome"], "view": world.view(save["state"]), "replay": True}

        self.expect(save, request)
        previous = save["state"]
        state, result = actions.resolve(previous, action)
        if state != previous:
            entry = {
                "revision": save["revision"] + 1, "request_id": key, "request_fingerprint": fingerprint,
                "command": command, "action": action, "mark_before": previous["tick"],
                "mark_after": state["tick"], "room": state["actor"]["room"],
                "outcome": {k: value for k, value in result.items() if k != "view"},
                "events": state["events"][len(previous["events"]):],
            }
            save = self.commit(save["profile"], save["run"], state, save["journal"], entry)
        return {**self.reference(save), **result}

    def start(self, index, profile, reason, receipt=None):
        state = baseline()
        world.witness_surroundings(state)
        row = index["profiles"][profile]
        if row["run"] is not None:
            row["archives"].append(row["run"])
        run = uuid.uuid4().hex
        row["run"] = run
        index.update(active=profile, reset=None)
        if receipt is not None:
            key, fingerprint = receipt
            index["admin_receipts"][key] = {"fingerprint": fingerprint, "profile": profile, "run": run}
        entry = {"revision": 0, "command": reason, "mark_before": 0, "mark_after": 0,
                 "room": world.room(state), "outcome": {"text": "The runner arrives at the Wayhouse."}}
        save = self.commit(profile, run, state, START, entry, index=index)
        return {**self.reference(save), "name": row["name"], "view": world.view(state)}

    def initialize(self):
        if self.index_path.exists() or any(self.root.glob("player_*")):
            raise RequestError("There are already player records here.")
        profile = "player_001"
        index = {"schema": 1, "active": profile, "next": 2, "reset": None, "admin_receipts": {},
                 "profiles": {profile: {"name": "Runner", "run": None, "archives": []}}}
        return self.start(index, profile, "INITIALIZE")

    def reset_request(self, request):
        index = self.index()
        save, _ = self.load(index)
        self.expect(save, request)
        index["reset"] = self.reference(save)
        atomic_json(self.index_path, index)
        return {"confirmation_required": True, "name": index["profiles"][save["profile"]]["name"]}

    def cancel_reset(self):
        index = self.index()
        index["reset"] = None
        atomic_json(self.index_path, index)
        return {"cancelled": True}

    def new_run(self, operation, request):
        key = request_id(request)
        index = self.index()
        save, _ = self.load(index)
        previous = index["admin_receipts"].get(key)
        fingerprint = state_digest({"op": operation, "request": request})
        if previous is not None:
            if previous["fingerprint"] != fingerprint:
                raise RequestError("That retry key belongs to a different administrative request.")
            if (save["profile"], save["run"], save["revision"]) != (previous["profile"], previous["run"], 0):
                raise RequestError("The new run already started and the active state has since changed.")
            name = index["profiles"][save["profile"]]["name"]
            return {**self.reference(save), "name": name, "view": world.view(save["state"]), "replay": True}

        self.expect(save, request)
        if operation == "confirm-reset" and index["reset"] != self.reference(save):
            raise RequestError("There is no confirmation pending for the current playthrough state.")
        profile = save["profile"]
        if operation == "new-player":
            profile = f"player_{index['next']:03d}"
            name = request.get("name")
            if name is None:
                name = f"Player {index['next']}"
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64 or not all(c.isprintable() for c in name):
                raise RequestError("Use a display name of 1 to 64 printable characters.")
            name = name.strip()
            used = {value.casefold() for ident, row in index["profiles"].items() for value in (ident, row["name"])}
            if name.casefold() in used or PROFILE_ID.fullmatch(name.casefold()):
                raise RequestError("That display name is already in use or reserved for profile identifiers.")
            index["profiles"][profile] = {"name": name, "run": None, "archives": []}
            index["next"] += 1
        return self.start(index, profile, operation.upper().replace("-", " "), (key, fingerprint))

    def switch(self, request):
        index = self.index()
        selector = request.get("name")
        if not isinstance(selector, str):
            raise RequestError("Specify a player by display name or profile identifier.")
        for profile, record in index["profiles"].items():
            if selector.casefold().strip() in {profile, record["name"].casefold()}:
                candidate = {**index, "active": profile, "reset": None}
                self.load(candidate)
                atomic_json(self.index_path, candidate)
                return self.status()
        raise RequestError("There is no player with that name or identifier.")


def main():
    parser = argparse.ArgumentParser(description="Structured save operations for Codex")
    parser.add_argument("operation", choices=("initialize", "context", "view", "status", "profiles",
                        "turn", "new-game", "new-player", "switch", "request-reset", "confirm-reset",
                        "cancel-reset"))
    parser.add_argument("payload", nargs="?", help="Base64-encoded UTF-8 JSON")
    args = parser.parse_args()
    try:
        payload = json.loads(base64.b64decode(args.payload, validate=True)) if args.payload else {}
        if not isinstance(payload, dict):
            raise RequestError("The payload must be a JSON object.")
        with Store(ROOT / "players").session() as game:
            if args.operation == "turn":
                result = game.turn(payload)
            elif args.operation in {"new-game", "new-player", "confirm-reset"}:
                result = game.new_run(args.operation, payload)
            elif args.operation == "switch":
                result = game.switch(payload)
            elif args.operation == "request-reset":
                result = game.reset_request(payload)
            elif args.operation == "cancel-reset":
                result = game.cancel_reset()
            elif args.operation == "view":
                result = game.context()["view"]
            elif args.operation == "initialize":
                result = game.initialize()
            else:
                public_reads = {"context": game.context, "status": game.status, "profiles": game.profiles}
                result = public_reads[args.operation]()
        print(json.dumps(result, ensure_ascii=True))
    except RequestError as error:
        print(json.dumps({"request_error": str(error)}))
        return 2
    except (OSError, ValueError, KeyError, TypeError, SaveError) as error:
        print(json.dumps({"technical_error": type(error).__name__, "detail": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
