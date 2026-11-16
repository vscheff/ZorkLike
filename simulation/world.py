"""Fixed geography, state projection and effects of the regulating bell."""

import json
from pathlib import Path

GAME = Path(__file__).resolve().parents[1] / "game"
WORLD = json.loads((GAME / "WORLD.json").read_text(encoding="utf-8"))
REGION = {room: region for region, rooms in WORLD["regions"].items() for room in rooms}
ROOMS = {room: name for rooms in WORLD["regions"].values() for room, name in rooms.items()}
OBJECTS = WORLD["objects"]
PEOPLE = WORLD["people"]
FIXTURES = WORLD["fixtures"]
DARK = set(WORLD["dark"])
UNDER_RISK = set(WORLD["under_risk"])
WASH = WORLD["wash"]
TIDE = (0, 0, 0, 1, 2, 3, 3, 3, 2, 1, 0, 0)
CAPACITY = 12
EXITS = {room: {} for room in ROOMS}
HOLDERS = {
    "hatch_taper": "weigh_room",
    "hatch_pan": "weigh_room",
    "drive_socket": "winding_gallery",
    "scratch_frame": "recorder_room",
    "east_packing": "rain_trough",
    "west_socket": "west_head",
    "address_slot": "address_wall",
    "union_board": "union_room",
}
HIDDEN_PATHS = {"inlet": "inlet_eye", "loft": "loft_open"}
BEARING_ENTRIES = {"bearing_gate", "daywell", "grate_road"}
CRADLE_ROOMS = {"hatch_well", "blind_cradle", "under_ledge"}
RETURN_LIGHT = {"hatch_well", "under_ledge", "blind_cradle", "uphill_gap"}
LOOPS = (11, 19, 27)
MERA_EVACUATION = {
    "occupied_sill": "low_kitchen", "address_wall": "cloth_door",
    "cloth_door": "low_kitchen", "low_kitchen": "uphill_gap",
    "uphill_gap": "root_stair", "root_stair": "glass_path",
}


for a, outbound, b, inbound, *terrain in WORLD["edges"]:
    gate = terrain[0] if terrain else None
    if outbound in EXITS[a] or inbound in EXITS[b]:
        raise ValueError("Duplicate direction in canonical geography")
    EXITS[a][outbound] = (b, gate)
    EXITS[b][inbound] = (a, gate)


def room(state):
    return state["actor"]["room"]


def tide(state):
    return TIDE[state["tick"] % len(TIDE)]


def add_unique(values, value):
    if value not in values:
        values.append(value)


def path_id(a, b):
    return "/".join(sorted((a, b)))


def present(state, person):
    record = state["people"][person]
    if not record["alive"]:
        return None
    return record.get("site") or PEOPLE[person]["route"][record["phase"]]


def carried(state, item):
    obj = state["objects"][item]
    return obj["at"] == "carry" and obj["condition"] == "intact"


def burden(state):
    return sum(spec["bulk"] for item, spec in OBJECTS.items() if carried(state, item))


def holder_has(state, holder):
    return [item for item, obj in state["objects"].items()
            if obj["at"] == holder and obj["condition"] == "intact"]


def load(state, holder):
    return sum(OBJECTS[item]["load"] for item in holder_has(state, holder))


def in_room(state, item):
    at = state["objects"][item]["at"]
    return at == room(state) or HOLDERS.get(at) == room(state)


def illuminated(state):
    lamp = state["objects"]["lamp"]
    return (room(state) not in DARK
            or (state["lamp"]["lit"] and lamp["condition"] == "intact"
                and (carried(state, "lamp") or in_room(state, "lamp"))))


def path_revealed(state, gate):
    if gate == "inlet":
        return state["inlet_open"] or "inlet_eye" in state["knowledge"]["facts"]
    return gate not in HIDDEN_PATHS or state["loft_open"]


def path_obstruction(state, dest, gate):
    if state["transfer"]["collapsed"] and dest in UNDER_RISK:
        return "The way ends in broken stone."
    if gate == "hatch" and room(state) == "weigh_room":
        if not state["hatch_wedged"] and load(state, "hatch_pan") < 6:
            return "The hatch lifts a fraction. The latch is still caught."
    if gate in {"shoal", "inlet"} and tide(state) >= 2:
        return "Water is running too hard over the footing."
    if gate == "inlet" and not state["inlet_open"]:
        return "The inlet grille is down in its seat."
    if gate == "root" and not state["root_open"]:
        return "The grille stays against its catch."
    if gate == "stack" and not state["stack_open"]:
        return "The back door is latched."
    if gate in {"bearing", "bearing_in"} and not state["filing"]["bearing_open"]:
        return "The interlock bar stays drawn."
    if gate in {"lift_top", "lift_bottom"}:
        cradle = state["cradle"]
        landing = "up" if gate == "lift_top" else "down"
        if cradle["due"] is not None:
            return "The cage is moving somewhere in the shaft."
        if cradle["position"] != landing:
            return "The cage is at the other stop."
    return None


def witness_surroundings(state):
    knowledge = state["knowledge"]
    add_unique(knowledge["rooms"], room(state))
    if illuminated(state):
        for item in OBJECTS:
            if in_room(state, item):
                add_unique(knowledge["seen"], item)
        for fixture, record in FIXTURES.items():
            if record["at"] == room(state) and (fixture != "inlet_eye" or path_revealed(state, "inlet")):
                add_unique(knowledge["seen"], fixture)


def view(state):
    """A local projection for the narrator. The room ID and tick support adjudication."""
    here = room(state)
    light = illuminated(state)
    paths = {}
    for direction, (dest, gate) in EXITS[here].items():
        if not path_revealed(state, gate):
            continue
        familiar = path_id(here, dest) in state["knowledge"]["paths"]
        if light or familiar or dest in {"cloth_door", "low_kitchen", "glass_path"}:
            paths[direction] = {
                "known_destination": ROOMS[dest] if familiar else None,
                "obstruction": path_obstruction(state, dest, gate) if light else None,
            }

    objects = {item: OBJECTS[item]["name"] for item in OBJECTS if light and in_room(state, item)}
    fixtures = {item: spec["name"] for item, spec in FIXTURES.items()
                if light and spec["at"] == here and (item != "inlet_eye" or path_revealed(state, "inlet"))}
    people = {person: PEOPLE[person]["name"] if person in state["knowledge"]["met"] else None
              for person in PEOPLE if present(state, person) == here}
    gauges = {}
    if here in {"sill_walk", "wash_step", "ferry_head", "catchgate", "sluice_shelf",
                "brine_lip", "gauge_nook", "tail_drain", "east_head", "west_head", "recorder_room",
                "commit_cage", "observing_bridge"}:
        gauges["water"] = tide(state)
    if here in CRADLE_ROOMS or here == "winding_gallery":
        gauges["cage_moving"] = state["cradle"]["due"] is not None
        if light or here == "blind_cradle":
            gauges["cage_stop"] = state["cradle"]["position"]
    if here == "recorder_room":
        gauges["scratch"] = state["scratch"].copy()
        if gauges["scratch"]["due"] is not None:
            gauges["scratch"]["marks_left"] = gauges["scratch"]["due"] - state["tick"]
        del gauges["scratch"]["surged"]
    if here == "east_head":
        gauges["east_beads"] = state["east"]["charge"]
        gauges["east_seated"] = state["east"]["seated"]
    if here == "rain_trough":
        gauges["valve_open"] = state["east"]["valve"]
        gauges["packed"] = bool(holder_has(state, "east_packing"))
    if here == "west_head":
        gauges["west_vent"] = state["west"]["vent"]
        gauges["west_seated"] = state["west"]["seated"]
        gauges["west_broken"] = state["west"]["broken"]
    if here == "selector_aisle":
        gauges["selector"] = state["selector"].copy()
        gauges["locked"] = state["transfer"]["stage"] == "running"
    if here in {"balance_deck", "commit_cage", "observing_bridge", "quiet_cell"}:
        gauges["works"] = state["transfer"]["stage"]
        if here == "commit_cage" and state["transfer"]["stage"] == "running":
            gauges["teeth_left"] = state["transfer"]["remaining"]
    if here in {"west_shore", "west_head", "span_foot"}:
        gauges["west_discharge_visible"] = state["west"]["spilled"]
    if here in {"rain_orchard", "east_berm", "east_head", "seed_loft"}:
        gauges["east_discharge_visible"] = state["east"]["spilled"]
    if REGION[here] == "underbody":
        gauges["collapse_visible"] = state["transfer"]["collapsed"]
        gauges["settled"] = state["transfer"]["stage"] == "complete"

    return {
        "room": here, "title": ROOMS[here] if light else None, "light": light,
        "exits": paths, "objects": objects, "fixtures": fixtures, "people": people,
        "inventory": [OBJECTS[item]["name"] for item in OBJECTS if carried(state, item)],
        "gauges": gauges, "health": state["actor"]["health"],
        "tick": state["tick"], "status": state["actor"]["status"],
    }


def record(state, event, **details):
    state["events"].append({"mark": state["tick"], "event": event, **details})


def lose(state, item, condition="lost"):
    obj = state["objects"][item]
    obj.update(at="gone", condition=condition)
    if item == "lamp":
        state["lamp"]["lit"] = False
        state["lamp"]["fuel"] = 0
    if item == "oil_tin":
        state["lamp"]["reserve"] = 0


def hurt(state, amount, cause):
    actor = state["actor"]
    if actor["status"] == "dead":
        return
    actor["health"] = max(0, actor["health"] - amount)
    if actor["health"] == 0:
        actor.update(status="dead", end=cause)
        record(state, "death", cause=cause, room=room(state))


def warn_ready(state, group):
    due = state["warnings"][group]
    return due is not None and state["tick"] >= due


def collapse(state, cause, audible):
    transfer = state["transfer"]
    transfer.update(stage="failed", remaining=0, old_link=False, active_line=None, collapsed=True)
    record(state, "bearing_collapse", cause=cause,
           households_clear=warn_ready(state, "below"))
    mera = present(state, "mera")
    if not warn_ready(state, "below") and mera in UNDER_RISK:
        state["people"]["mera"]["alive"] = False
    elif mera is not None and state["warnings"]["below"] is None:
        state["people"]["mera"]["site"] = mera
    if room(state) in UNDER_RISK:
        hurt(state, 3, "collapse")
        audible.append("The ceiling drops before the next knock.")
    elif REGION[room(state)] in {"underbody", "bearing", "wayhouse"}:
        audible.append("There is a deep report from beneath the basin. The next knock never comes.")


def bed_ready(state, bed):
    if bed == "east":
        return (state["east"]["seated"] and state["east"]["charge"] == 3
                and bool(holder_has(state, "east_packing")))
    return (state["west"]["seated"] and state["west"]["vent"] == "river"
            and not state["west"]["broken"] and bool(holder_has(state, "west_socket")))


def transfer_pulse(state, level, audible):
    transfer = state["transfer"]
    if transfer["stage"] != "running":
        return
    bed = transfer["bed"]
    if level >= 2 or not transfer["old_link"] or not bed_ready(state, bed):
        cause = "surge" if level >= 2 else "unseated"
        collapse(state, cause, audible)
        return
    transfer["remaining"] -= 1
    if room(state) in {"balance_deck", "commit_cage"}:
        audible.append("One tooth drops in the shaft.")
    if transfer["remaining"] != 0:
        return
    transfer.update(stage="complete", active_line=bed, old_link=False)
    state[bed]["spilled"] = True
    state["objects"]["closing_band"]["at"] = "commit_cage"
    if bed == "east" and state["objects"]["seed_box"]["at"] == "seed_loft":
        lose(state, "seed_box", "ruined")
    record(state, "transfer_complete", bed=bed, warned=warn_ready(state, bed))
    if room(state) == "commit_cage":
        audible.append("The old dog opens with a flat click. A bright band slides out of the slot.")
    elif here_sees_discharge(state, bed):
        audible.append("The relief channel gives a sudden roar.")


def here_sees_discharge(state, bed):
    if bed == "east":
        return room(state) in {"observing_bridge", "east_head", "east_berm", "rain_orchard"}
    return room(state) in {"observing_bridge", "west_head", "west_shore", "span_foot"}


def step(state, audible):
    state["tick"] += 1
    now = state["tick"]
    level = tide(state)
    for person, entry in state["people"].items():
        if not entry["alive"]:
            continue
        if person == "mera" and state["warnings"]["below"] is not None:
            here = present(state, person)
            if here != "uphill_gap" or state["root_open"]:
                entry["site"] = MERA_EVACUATION.get(here, here)
        elif not entry.get("site"):
            entry["phase"] = (entry["phase"] + 1) % len(PEOPLE[person]["route"])

    lamp = state["lamp"]
    if lamp["lit"]:
        lamp["fuel"] -= 1
        if lamp["fuel"] == 0:
            lamp["lit"] = False
            if carried(state, "lamp") or in_room(state, "lamp"):
                audible.append("The lamp coughs and goes out.")

    cradle = state["cradle"]
    if cradle["due"] == now:
        cradle.update(position=cradle["target"], target=None, due=None)
        if room(state) in CRADLE_ROOMS or room(state) == "winding_gallery":
            audible.append("The cage settles against its stop.")

    scratch = state["scratch"]
    if scratch["due"] is not None:
        scratch["surged"] |= level >= 2
        if scratch["due"] == now:
            reading = "blurred" if scratch["surged"] else f"trace{scratch['loop']}"
            state["objects"]["recorder_leaf"]["reading"] = reading
            scratch.update(due=None, surged=False)
            if room(state) == "recorder_room":
                audible.append("The last finger on the counting wheel drops.")

    east = state["east"]
    if not east["seated"]:
        if east["valve"] and holder_has(state, "east_packing") and level >= 2:
            east["charge"] = min(3, east["charge"] + 1)
        elif not east["valve"] and level == 0:
            east["charge"] = max(0, east["charge"] - 1)

    below_due = state["warnings"]["below"]
    if below_due is not None and now <= below_due and not state["root_open"]:
        state["warnings"]["below"] += 1
    for group, due in state["warnings"].items():
        if due == now:
            record(state, "warning_complete", group=group)
    transfer_pulse(state, level, audible)
    if state["actor"]["status"] == "playing":
        wash(state, level, audible)


def wash(state, level, audible):
    here = room(state)
    if here not in WASH or level < 2:
        return
    if level == 3:
        audible.append("Water shuts over the rail and leaves nowhere to draw breath.")
        hurt(state, 3, "flood")
        return
    for item in OBJECTS:
        if in_room(state, item) and state["objects"][item]["at"] == here:
            lose(state, item)
    for item in ("lamp", "recorder_leaf"):
        if carried(state, item):
            lose(state, item, "ruined")
            audible.append(f"The water takes the {OBJECTS[item]['name']}.")
    state["actor"]["room"] = WASH[here]
    hurt(state, 1, "flood")
    record(state, "wash", from_room=here, to_room=room(state))
    audible.append("The rise lifts you off your feet and throws you onto the higher apron.")


def completed(state):
    transfer = state["transfer"]
    bed = transfer["bed"]
    band = state["objects"]["closing_band"]
    return (
        state["actor"]["status"] == "playing" and state["actor"]["health"] > 0
        and state["filing"]["issued"] and state["filing"]["bearing_open"]
        and state["filing"]["returned"] and room(state) == "address_wall"
        and band["at"] == "address_slot" and band["condition"] == "intact"
        and transfer["stage"] == "complete" and transfer["remaining"] == 0
        and not transfer["old_link"] and not transfer["collapsed"]
        and bed in {"east", "west"} and transfer["active_line"] == bed and state[bed]["spilled"]
    )


def ending(state):
    bed = state["transfer"]["bed"]
    commissioning = next(event for event in reversed(state["events"])
                         if event["event"] == "transfer_complete")
    seed_box = state["objects"]["seed_box"]
    seed_stock = "spoiled" if seed_box["condition"] != "intact" else "viable"
    if seed_stock == "viable" and seed_box["at"] == "shed_roof":
        seed_stock = "on_roof"
    return {
        "bed": bed,
        "warned": commissioning["warned"],
        "seed_stock": seed_stock,
        "published": state["rent_posted"],
    }
