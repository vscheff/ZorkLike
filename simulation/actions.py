"""Resolve one structured action already interpreted by Codex."""

import re
from copy import deepcopy
from typing import NamedTuple

import world as w


class Attempt(NamedTuple):
    text: str
    marks: int = 1


class Refusal(Exception):
    def __init__(self, text, marks):
        super().__init__(text)
        self.marks = marks


def require(condition, text, marks=1):
    if not condition:
        raise Refusal(text, marks)


def at(state, *places):
    require(w.room(state) in places, "There is nothing within reach to do that with.", 0)


def need(state, item):
    require(w.carried(state, item), f"You aren't holding the {w.OBJECTS[item]['name']}.", 0)


def item_id(action):
    item = action.get("item")
    require(item in w.OBJECTS, "Which thing do you mean?", 0)
    return item


def seen(state, fact):
    w.add_unique(state["knowledge"]["facts"], fact)


def give_room(state, item, place=None):
    state["objects"][item]["at"] = place or w.room(state)
    w.add_unique(state["knowledge"]["seen"], item)


def walk(state, action):
    here = w.room(state)
    direction = action.get("direction")
    edge = w.EXITS[here].get(direction)
    require(edge and w.path_revealed(state, edge[1]), "You find no way in that direction.", 0)
    dest, gate = edge
    path = w.path_id(here, dest)
    known = path in state["knowledge"]["paths"]
    easy_in_dark = dest not in w.DARK or {here, dest} <= w.RETURN_LIGHT
    require(w.illuminated(state) or known or easy_in_dark or action.get("feel") is True,
            "You can't see a way through. The nearest stone is within feel of your hand.", 0)

    obstruction = w.path_obstruction(state, dest, gate)
    if obstruction:
        if gate in {"shoal", "inlet"} and w.tide(state) >= 2 and action.get("force") is True:
            exposed = dest if dest in w.WASH else here if here in w.WASH else None
            require(exposed and (gate != "inlet" or state["inlet_open"]), obstruction)
            state["actor"]["room"] = exposed
            audible = []
            w.wash(state, w.tide(state), audible)
            return Attempt(" ".join(audible))
        raise Refusal(obstruction, 1)

    w.add_unique(state["knowledge"]["paths"], path)
    state["actor"]["room"] = dest
    if gate == "long":
        return Attempt("You cross the long span.", 2)
    if gate == "hatch" and here == "hatch_well" and w.load(state, "hatch_pan") < 6:
        return Attempt("You slip the latch from below and climb. It clicks shut behind you.")
    if not w.illuminated(state):
        return Attempt("You move into the dark.")
    return Attempt("")


def detach(state, item, position):
    if position == "drive_socket":
        require(state["cradle"]["due"] is None, "The drive cover is locked over the moving lugs.")
    if position == "scratch_frame" and state["scratch"]["due"] is not None:
        state["scratch"].update(due=None, surged=False)
    if position == "hatch_taper":
        state["hatch_wedged"] = False
    if position == "west_socket":
        require(not state["west"]["seated"], "The test jack is bearing on the shoe.")
    if position == "east_packing":
        require(state["transfer"]["active_line"] != "east", "The live gland is clamped under load.")
        state["east"]["seated"] = False
    if position == "address_slot":
        raise Refusal("The socket has locked shut over the band.", 1)


def take(state, action):
    item = item_id(action)
    obj = state["objects"][item]
    require(not w.carried(state, item), "You're already holding it.", 0)
    require(w.in_room(state, item) and obj["condition"] == "intact",
            "You can't reach that here.", 0)
    can_find = item in state["knowledge"]["seen"] and action.get("feel") is True
    require(w.illuminated(state) or can_find, "Your hand finds only the dark.", 1)
    require(w.burden(state) + w.OBJECTS[item]["bulk"] <= w.CAPACITY,
            "You can't hold it with everything else you're carrying.", 1)
    old_position = obj["at"]
    detaching_trace = old_position == "scratch_frame" and state["scratch"]["due"] is not None
    detach(state, item, old_position)
    give_room(state, item, "carry")
    note = " The counting wheel springs back." if detaching_trace else ""
    return Attempt(f"Taken.{note}")


def drop(state, action):
    item = item_id(action)
    need(state, item)
    give_room(state, item)
    return Attempt("Dropped.")


def place(state, action):
    item = item_id(action)
    target = action.get("target")
    at(state, w.HOLDERS.get(target))
    obj = state["objects"][item]
    on_floor = obj["at"] == w.room(state) and obj["condition"] == "intact"
    require(w.carried(state, item) or (on_floor and w.illuminated(state)),
            "You don't have it within reach.", 0)
    holders = w.holder_has(state, target)

    if target == "hatch_pan":
        require(len(holders) < 3, "There is no flat space left in the pan.")
        give_room(state, item, target)
        if w.load(state, target) >= 6:
            return Attempt("The counterpan sinks past the sixth division. The hatch latch rises.")
        return Attempt("The pointer rises on the scale. The latch is still down.")

    if target == "hatch_taper":
        require(w.OBJECTS[item].get("tool") == "wedge", "It won't hold in the tapered gap.")
        require(w.load(state, "hatch_pan") >= 6 and not state["hatch_wedged"],
                "There is no open gap under the catch to prop.")
        give_room(state, item, target)
        state["hatch_wedged"] = True
        return Attempt("The shim fits between the raised catch and its shoulder.")

    if target == "drive_socket":
        require(item in {"pawl", "rigging"} and not holders,
                "The two unequal lugs won't take it like that.")
        require(state["cradle"]["due"] is None, "The drive is turning.")
        give_room(state, item, target)
        return Attempt("Both lugs catch. The call chain takes up its slack.")

    if target == "scratch_frame":
        require(item == "recorder_leaf" and not holders, "It won't sit square in the clip.")
        give_room(state, item, target)
        return Attempt("The spring clip snaps down flat.")

    if target == "east_packing":
        suitable = item == "packing_cord" or (item == "rag" and state["objects"][item].get("waxed"))
        require(suitable and not holders, "It won't make a continuous seal around the spindle.")
        give_room(state, item, target)
        return Attempt("The pack closes all around the spindle.")

    if target == "west_socket":
        require(item == "shoe" and not holders and not state["west"]["broken"],
                "It won't sit soundly under the heel.")
        give_room(state, item, target)
        return Attempt("The corners of the shoe come up flush.")

    raise Refusal("There is no way to fit it there.", 0)


def call_cradle(state, action):
    at(state, *w.CRADLE_ROOMS, "winding_gallery")
    target = action.get("setting")
    require(target in {"up", "down"}, "Which stop, upper or lower?", 0)
    cradle = state["cradle"]
    require(cradle["due"] is None, "The calling chain has gone taut. The cage is moving.")
    require(w.holder_has(state, "drive_socket"), "The chain moves freely and brings nothing with it.")
    require(cradle["position"] != target, "The cage is already at that stop.", 0)
    if target == "down":
        require(not state["transfer"]["collapsed"], "The lower stop feels jammed in its shaft.")
    cradle.update(target=target, due=state["tick"] + 3)
    return Attempt("The chain takes the weight. A grind starts in the shaft.")


def reach_tool(state, action):
    item = item_id(action)
    need(state, item)
    require(w.OBJECTS[item].get("tool") == "reach", "It won't reach around the turn.")


def open_inlet(state, action):
    at(state, "sluice_shelf", "return_duct")
    require(w.tide(state) < 2, "Water is bearing too hard on the grille to lift it.")
    reach_tool(state, action)
    seen(state, "inlet_eye")
    if action.get("setting") == "shut":
        state["inlet_open"] = False
        return Attempt("The eye lowers. The grille drops into its seat.")
    state["inlet_open"] = True
    return Attempt("The eye comes up and rests against its stop. The iron throat is open.")


def get_loft(state, action):
    at(state, "post_loft")
    reach_tool(state, action)
    seen(state, "loft_gap")
    require(state["objects"]["ferry_key"]["at"] == "cache_loft",
            "The slot is empty where you reach.")
    give_room(state, "ferry_key")
    return Attempt("A flat key skitters over the boards and lands by your boot.")


def open_loft(state, action):
    at(state, "post_loft")
    reach_tool(state, action)
    if action.get("setting") == "shut":
        state["loft_open"] = False
        return Attempt("The boards slide back. The pintle drops.")
    state["loft_open"] = True
    return Attempt("The boards slide aside. Thin planks lead east over the roof.")


def open_ferry(state, action):
    at(state, "old_ferry")
    need(state, "ferry_key")
    require(not state["ferry_open"], "The ferry box stands open.", 0)
    state["ferry_open"] = True
    for item in ("ferry_list", "old_counter"):
        give_room(state, item)
    return Attempt("The lid comes up. Inside lie a passenger sheet and a splintered fare counter.")


def open_stack(state, action):
    at(state, "reverse_stack")
    state["stack_open"] = True
    return Attempt("The west side of the public stack is open from here now.")


def pry_docket(state, action):
    at(state, "reverse_stack")
    need(state, "shim")
    require(state["objects"]["rent_carbon"]["at"] == "cache_docket", "The floor of the drawer is bare.")
    give_room(state, "rent_carbon")
    return Attempt("The false floor rises. An old sheet of writing cloth comes free.")


def open_root(state, action):
    if action.get("setting") == "shut":
        at(state, "uphill_gap", "root_stair")
        require(state["root_open"], "The grille is already shut.", 0)
        state["root_open"] = False
        return Attempt("The grille swings back. You hear the latch catch on the lower side.")
    at(state, "uphill_gap")
    state["root_open"] = True
    return Attempt("The thumb latch lifts. The grille stays back against the root wall.")


def open_foil(state, action):
    at(state, "address_wall")
    require(state["objects"]["spare_foil"]["at"] == "cache_foil", "The shallow groove is empty.")
    seen(state, "foil_cache")
    give_room(state, "spare_foil")
    return Attempt("The tile rocks free. Behind it is an old strip of soft foil.")


def press_foil(state, action):
    at(state, "settlement_shaft")
    need(state, "spare_foil")
    require(not state["transfer"]["collapsed"], "The blades no longer meet the pad.")
    state["objects"]["spare_foil"]["reading"] = "witness19"
    return Attempt("Six small dents surround a pair of close pricks and a wider one.")


def recorder_loop(state, action):
    at(state, "recorder_room")
    setting = action.get("setting")
    require(setting in w.LOOPS, "The dial has three stops, 11, 19 and 27.", 0)
    require(state["scratch"]["due"] is None, "The dial is held by the counting wheel.")
    state["scratch"]["loop"] = setting
    return Attempt(f"The needle seats at {setting}.")


def draw(state, action):
    at(state, "recorder_room")
    require(w.holder_has(state, "scratch_frame"), "The clip is empty.")
    scratch = state["scratch"]
    require(scratch["due"] is None, "The counting wheel is still turning.")
    state["objects"]["recorder_leaf"]["reading"] = None
    scratch.update(due=state["tick"] + 3, surged=w.tide(state) >= 2)
    return Attempt("The first of three fingers climbs onto the wheel.")


def file_claim(state, action):
    at(state, "hearing_floor")
    require(not state["filing"]["issued"], "The press's stroke for this claim is spent.", 0)
    item = action.get("item")
    require(item in {"witness_strip", "spare_foil"}, "Which strip goes in the impression slot?", 0)
    require(w.carried(state, item) and w.carried(state, "recorder_leaf"),
            "Both originals have to be under the guides.")
    require(state["objects"][item]["reading"] == "witness19"
            and state["objects"]["recorder_leaf"]["reading"] == "trace19",
            "The test teeth touch the two faces and stop. The output tray stays empty.")
    state["filing"]["issued"] = True
    give_room(state, "writ")
    return Attempt("The lever goes home and returns both originals. A perforated strip drops into the output tray.")


def admit_writ(state, action):
    at(state, *w.BEARING_ENTRIES)
    need(state, "writ")
    require(state["filing"]["issued"], "The strip passes the first tooth and catches.")
    state["filing"]["bearing_open"] = True
    return Attempt("The strip comes back with a notch. Beyond it a long bar withdraws.")


def east_valve(state, action):
    at(state, "rain_trough")
    setting = action.get("setting")
    require(setting in {"open", "shut"}, "Turn it open or shut?", 0)
    state["east"]["valve"] = setting == "open"
    if setting == "open" and not w.holder_has(state, "east_packing"):
        return Attempt("Water leaks around the spindle.")
    return Attempt(f"The handle turns to {setting}.")


def east_seat(state, action):
    at(state, "east_head")
    require(state["east"]["charge"] == 3 and w.holder_has(state, "east_packing"),
            "The jack rises a little and settles back. The float isn't full.")
    state["east"]["seated"] = True
    return Attempt("The jack lifts the shoe under the arch and the captive lock falls behind it.")


def west_vent(state, action):
    at(state, "west_head")
    setting = action.get("setting")
    require(setting in {"river", "hold"}, "Which way, RIVER or HOLD?", 0)
    require(state["transfer"]["active_line"] != "west", "The live bleed handle is held by its stop.")
    state["west"]["vent"] = setting
    if setting == "hold":
        state["west"]["seated"] = False
    return Attempt(f"The bleed lever turns to {setting.upper()}.")


def west_test(state, action):
    at(state, "west_head")
    west = state["west"]
    require(not west["broken"], "The heel is split. The test wheel has lost its purchase.")
    require(w.holder_has(state, "west_socket"), "The test wheel turns against an empty heel.")
    if w.tide(state) >= 2 and west["vent"] == "hold":
        if action.get("force") is True:
            west.update(broken=True, seated=False)
            w.lose(state, "shoe", "ruined")
            w.record(state, "heel_split")
            return Attempt("The wheel gives. A crack runs through the heel and opens across the shoe.")
        return Attempt("The wheel stops against a hard back pressure.")
    require(w.tide(state) < 2 and west["vent"] == "river",
            "The test wheel has no travel left at this pressure.")
    west["seated"] = True
    return Attempt("The wheel goes through. A mouthful of gray water runs out of the bleed.")


def select(state, action):
    at(state, "selector_aisle")
    require(state["transfer"]["stage"] != "running", "The dials are locked against the live stroke.")
    loop, bed = action.get("loop"), action.get("bed")
    require(loop is not None or bed is not None, "What loop or bed do you set?", 0)
    require(loop is None or loop in w.LOOPS, "The loop dial has no stop there.", 0)
    require(bed is None or bed in {"east", "west"}, "The lever has only EAST EARTH and WEST STONE.", 0)
    if loop is not None:
        state["selector"]["loop"] = loop
    if bed is not None:
        state["selector"]["bed"] = bed
    return Attempt("The selector rests in its notch.", 2 if loop is not None and bed is not None else 1)


def engage(state, action):
    at(state, "commit_cage")
    transfer = state["transfer"]
    require(transfer["stage"] == "idle" and transfer["old_link"],
            "The engage shaft cannot catch the old dog.")
    require(state["selector"]["loop"] == 19 and state["filing"]["bearing_open"],
            "The lever stops at the selector's interlock.")
    bed = state["selector"]["bed"]
    require(w.bed_ready(state, bed), "The lever moves to a blank stop. No seat answers.")
    # The pressure can be felt before the pin goes over center. An explicit
    # insistence is needed to force the draw on present high head.
    require(w.tide(state) < 2 or action.get("force") is True,
            "The lever comes up against a hard pressure before the pin moves.")
    transfer.update(stage="running", remaining=3, bed=bed)
    w.record(state, "transfer_engaged", bed=bed)
    if w.tide(state) >= 2:
        audible = []
        w.collapse(state, "pressure_at_engagement", audible)
        return Attempt(" ".join(audible))
    return Attempt("The pin slips over center. The shaft starts down.")


def stop(state, action):
    at(state, "commit_cage")
    require(state["transfer"]["stage"] == "running", "There is no live stroke for the black stop to hold.")
    state["transfer"].update(stage="idle", remaining=0, bed=None)
    w.record(state, "transfer_stopped")
    return Attempt("The black stop catches. The old dog still bears.")


def release_dog(state, action):
    at(state, "quiet_cell")
    require(state["transfer"]["old_link"], "The arm is already off its seat.", 0)
    audible = ["The arm sweeps sideways and catches you before you clear it."]
    w.hurt(state, 1, "dog_sweep")
    w.collapse(state, "manual_release", audible)
    return Attempt(" ".join(audible))


def post_return(state, action):
    at(state, "address_wall")
    need(state, "closing_band")
    require(state["transfer"]["stage"] == "complete", "The band won't seat.")
    give_room(state, "closing_band", "address_slot")
    state["filing"]["returned"] = True
    return Attempt("The band slides in all but a finger's width. A spring takes the unpunched end.")


MACHINES = {
    "call_cradle": call_cradle, "open_inlet": open_inlet, "get_loft": get_loft,
    "open_loft": open_loft, "open_ferry": open_ferry, "open_stack": open_stack,
    "pry_docket": pry_docket, "open_root": open_root, "open_foil": open_foil,
    "press_foil": press_foil, "recorder_loop": recorder_loop, "draw": draw,
    "file_claim": file_claim, "admit_writ": admit_writ, "east_valve": east_valve,
    "east_seat": east_seat, "west_vent": west_vent, "west_test": west_test,
    "select": select, "engage": engage, "stop": stop, "release_dog": release_dog,
    "post_return": post_return,
}


def machine(state, action):
    fn = MACHINES.get(action.get("kind"))
    require(fn is not None, "You don't find a way to do that.", 0)
    return fn(state, action)


DISCOVERIES = {
    "clerk_destination": ("vestibule",),
    "loft_gap": ("post_loft",),
    "inlet_eye": ("sluice_shelf", "return_duct"),
    "foil_cache": ("address_wall",),
    "loop_overlay": ("map_vault",),
    "old_link": ("sixth_pier", "quiet_cell", "occupied_sill"),
    "pier_mark": ("sixth_pier",),
    "bell_pattern": ("bell_bed", "return_duct"),
    "west_relief": ("west_head", "west_shore", "span_foot"),
    "east_relief": ("east_head", "east_berm", "seed_loft"),
    "tide_scale": ("gauge_nook",),
    "retired_address": ("sixth_step", "public_stack", "dead_letter"),
    "press_instructions": ("hearing_floor", "registry_entry"),
    "transfer_instructions": ("commit_cage",),
    "wooden_transfer_sample": ("pattern_room",),
}
TACTILE_FACTS = {"bell_pattern"}


def observe(state, action):
    method = action.get("method", "examine")
    require(method in {"examine", "read", "search", "listen", "feel"},
            "How are you trying to make it out?", 0)
    target = action.get("target")
    fact = action.get("fact")
    light = w.illuminated(state)
    if target in w.OBJECTS:
        obj = state["objects"][target]
        accessible = w.carried(state, target) or w.in_room(state, target)
        require(accessible and obj["condition"] == "intact", "That isn't within reach.", 0)
        require(method == "feel" or light, "There isn't enough light to make it out.", 0)
        if method == "read":
            require(w.OBJECTS[target].get("readable"), "There is nothing written there.", 0)
            w.add_unique(state["knowledge"]["read"], target)
            if obj.get("reading"):
                seen(state, f"{target}:{obj['reading']}")
        w.add_unique(state["knowledge"]["seen"], target)
    elif target in w.FIXTURES:
        fixture_rooms = {"inlet_eye": ("sluice_shelf", "return_duct"),
                         "root_grille": ("root_stair", "uphill_gap")}
        at(state, *fixture_rooms.get(target, (w.FIXTURES[target]["at"],)))
        require(light or method in {"feel", "listen"}, "There isn't enough light to make it out.", 0)
        w.add_unique(state["knowledge"]["seen"], target)
        if method == "read":
            w.add_unique(state["knowledge"]["read"], target)
    elif target is not None:
        raise Refusal("That isn't within reach.", 0)
    if fact is not None:
        require(w.room(state) in DISCOVERIES.get(fact, ()), "You can make out nothing more here.", 0)
        require(light or fact in TACTILE_FACTS, "It's too dark to make it out.", 0)
        seen(state, fact)
    return Attempt("", 0)


def handle_lamp(state, action):
    setting = action.get("setting")
    lamp = state["lamp"]
    require(w.carried(state, "lamp") or w.in_room(state, "lamp"), "The lamp isn't within reach.", 0)
    if setting == "light":
        require(lamp["fuel"] > 0, "The wick is dry.")
        require(not lamp["lit"], "It is already lit.", 0)
        lamp["lit"] = True
        return Attempt("The wick takes. A little yellow light gathers in the tin.")
    if setting == "snuff":
        require(lamp["lit"], "It is already out.", 0)
        lamp["lit"] = False
        return Attempt("The flame pinches out.")
    if setting == "refill":
        need(state, "oil_tin")
        require(not lamp["lit"], "The flame is over the mouth of the reservoir.")
        amount = min(18 - lamp["fuel"], lamp["reserve"])
        require(amount > 0, "The tin has nothing to add." if lamp["reserve"] == 0 else "The lamp is full.", 0)
        lamp["fuel"] += amount
        lamp["reserve"] -= amount
        return Attempt("You fill the little reservoir and screw the cap back on.")
    raise Refusal("Do what with the lamp?", 0)


def supply(state, action):
    at(state, "oil_room")
    item = item_id(action)
    need(state, item)
    if item == "oil_tin":
        state["lamp"]["reserve"] = 24
        return Attempt("The spigot fills the tin to its top seam.")
    if item == "rag":
        state["objects"]["rag"]["waxed"] = True
        return Attempt("The wax sinks into the folds. The cloth keeps its rolled shape.")
    raise Refusal("The stand has no fitting for that.", 0)


def bind(state, action):
    need(state, "bandage")
    require(state["actor"]["health"] < 3, "There is no injury to bind.", 0)
    w.lose(state, "bandage", "spent")
    state["actor"]["health"] += 1
    return Attempt("The clean linen takes some of the strain.")


DIALOGUE = {
    "mera": {
        "address": "“They changed the book. They didn't take down a door. We're all still here.”",
        "press": "“The number's on the pier where the wire goes. Our own weights go down the little blades into the press.”",
        "return": "“Where it ended up, that's where you put the return. At the wall with the six names.”",
    },
    "sile": {
        "filing": "“The press needs what the house bears and what the line carries, each on its own strip. It knows the difference.”",
        "absence": "“Vacancy was inferred from the closed crossing. It's still a valid inference on the copy in the forward stack.”",
        "works": "“Once you've passed the teeth at the works, the hearing doesn't tell you what to seat. That's your stroke.”",
    },
    "edra": {
        "cradle": "“Two lugs, both at once. That fork on my bench is cut to fit. A loop of chain in the peg guard might hold them too.”",
        "recorder": "“Wait for three fingers to fall. If the head's reached second black it'll scar the leaf on the side.”",
        "tide": "“Look at the cuts on the board by the winding stairs. No short draw likes going uphill through second black.”",
    },
    "kel": {
        "inlet": "“The small shelf has a lifted grille inside its rim. Easier to hook the eye if you can see the toe wear under it.”",
        "tide": "“First black's dry if you pick your feet up. Second black puts them somewhere else for you.”",
        "ferry": "“They paid fares there after the town said it was closed. You can say anything if you have the only book.”",
    },
    "nemi": {
        "lamp": "“Tap here. Use the tin, turn it till the top seam goes wet. Cold lamp only.”",
        "ferry": "“The old box took fares a half at a time, if you came in with a wet bundle. My thumb still remembers that broken counter.”",
    },
    "van": {
        "orchard": "“The new trees are where water was. Give it enough work and water remembers.”",
        "packing": "“Waxed cord by the outlets in the shed. Pack the split right round the spindle before you let high water in.”",
        "seeds": "“The bitter pear goes to the shed roof if the relief comes through. High in the loft isn't enough. There'll be steam in there.”",
    },
    "tave": {
        "rent": "“They kept the charge on the old mount after they took the names off. Show the order in their own words and I'll hang it.”",
        "meeting": "“The back room is for notices. Leave both sides of the table clear.”",
    },
    "iss": {
        "bleed": "“River before the test. HOLD is for a heel with no water on it. You won't have a second one if you wrench it at second black.”",
        "shore": "“You open that throat and the silt comes through my floors. Four marks gets the hand trucks to the other end of the span.”",
    },
}


def nearby_person(state, action):
    person = action.get("person")
    require(person in w.PEOPLE and w.present(state, person) == w.room(state),
            "There is nobody there to answer.", 0)
    return person, state["people"][person]


def talk(state, action):
    person, record = nearby_person(state, action)
    name = w.PEOPLE[person]["name"]
    knows = person in state["knowledge"]["met"]
    w.add_unique(state["knowledge"]["met"], person)
    intro = "" if knows else f"“{name}.” "
    topic = action.get("topic")
    if topic == "slip" and person == "mera":
        need(state, "return_slip")
        require(record["trust"] >= 0, "She glances at the seal without taking her hands off the bench.")
        if state["objects"]["witness_strip"]["at"] == "with_mera":
            drop_here = w.burden(state) >= w.CAPACITY
            give_room(state, "witness_strip", w.room(state) if drop_here else "carry")
            record["trust"] += 1
            text = "She lays a dimpled strip where you can take it." if drop_here else "She slips a dimpled strip into your hand."
            return Attempt(intro + "“Six. Yes, we're occupied.” " + text)
        return Attempt(intro + "“You've had the household strip from me already.”")
    if record["trust"] <= -2:
        return Attempt("They turn back to what they were doing.")
    if topic == "counter" and person == "nemi":
        need(state, "old_counter")
        seen(state, "nemi_ferry_account")
        record["trust"] = max(1, record["trust"])
        return Attempt(intro + "“There's the split. Six still paid me with it when the office said there was nobody to take across.”")
    line = DIALOGUE[person].get(topic)
    if line:
        seen(state, f"{person}:{topic}")
        return Attempt(intro + line)
    return Attempt(intro + "“I've a round to finish.”" if not knows else "You get a polite shake of the head.")


def warn(state, action):
    person, record = nearby_person(state, action)
    options = {
        "van": ("east", "east_relief", 4),
        "iss": ("west", "west_relief", 4),
        "mera": ("below", "old_link", 6),
    }
    require(person in options, "They look at you without an answer.")
    group, evidence, interval = options[person]
    require(record["trust"] >= 0, "They don't take it from you.")
    require(evidence in state["knowledge"]["facts"] or w.carried(state, "writ"),
            "“What have you seen that would make me put a hand on the bell?”")
    require(not state["warnings"][group], "“Word's gone round already.”", 0)
    if group == "below":
        require(state["root_open"] and not state["transfer"]["collapsed"],
                "“We'd have to get the high grille clear for that many feet.”")
    else:
        require(not state[group]["spilled"], "“It has already come through.”")
    state["warnings"][group] = state["tick"] + interval
    w.add_unique(state["knowledge"]["met"], person)
    w.record(state, "warning_given", group=group)
    return Attempt("They put down what they were holding and go to pass the word.")


def publish(state, action):
    at(state, "union_room")
    item = item_id(action)
    need(state, item)
    require(item in {"rent_carbon", "ferry_list"}, "The board is for evidence someone can read.")
    give_room(state, item, "union_board")
    if not state["rent_posted"] or item == "rent_carbon":
        state["rent_posted"] = item
    w.record(state, "public_record", item=item)
    return Attempt("You peg the sheet with the date facing out. People can make copies here.")


def ruin(state, action):
    item = item_id(action)
    position = state["objects"][item]["at"]
    require(w.carried(state, item) or w.in_room(state, item),
            "That isn't within reach.", 0)
    require(state["objects"][item]["condition"] == "intact", "There is nothing left to ruin.", 0)
    method = action.get("method")
    if method == "throw":
        water_sides = {*w.WASH, *w.WASH.values(), "ferry_head", "sill_walk", "pump_deck",
                       "brine_lip", "mussel_stair", "old_ferry", "observing_bridge", "west_shore"}
        require(w.room(state) in water_sides, "Nothing here would take it beyond reach.")
    else:
        require(method in {"smash", "tear"} and w.OBJECTS[item].get("fragile"),
                "It doesn't yield that way.")
    detach(state, item, position)
    if method == "throw":
        w.lose(state, item)
        return Attempt("It strikes once and disappears into the water.")
    w.lose(state, item, "ruined")
    return Attempt("What's left of it is of no more use.")


WAIT_GAUGES = {
    "low": ("water", lambda gauge: gauge < 2),
    "high": ("water", lambda gauge: gauge >= 2),
    "cradle": ("cage_moving", lambda gauge: not gauge),
    "draw": ("scratch", lambda gauge: gauge["due"] is None),
    "transfer": ("works", lambda gauge: gauge != "running"),
    "east_full": ("east_beads", lambda gauge: gauge == 3),
}


def wait(state, action):
    marks = action.get("marks", 1)
    require(type(marks) is int and 1 <= marks <= 48, "How many marks do you wait?", 0)
    until = action.get("until")
    if until is not None:
        test = watch(state, action)
        if test(state) and not action.get("next"):
            return Attempt("That has already come to pass.", 0)
    return Attempt("You wait.", marks)


def watch(state, action):
    until = action["until"]
    if until == "person":
        person = action.get("person")
        require(person in w.PEOPLE, "Whom do you wait for?", 0)
        return lambda saved: w.present(saved, person) == w.room(saved)
    require(until in WAIT_GAUGES, "You have no way to watch for that here.", 0)
    key, ready = WAIT_GAUGES[until]
    require(key in w.view(state)["gauges"], "You have no way to watch for that here.", 0)
    return lambda saved: ready(w.view(saved)["gauges"][key])


def adjudicate(state, action):
    marks = action.get("marks", 1)
    text = action.get("text")
    require(type(marks) is int and 0 <= marks <= 4 and isinstance(text, str) and len(text) <= 2000,
            "You stop before doing anything further.", 0)
    detail = action.get("detail")
    if detail is not None:
        key = detail.get("id", "")
        require(re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key) and "value" in detail,
                "That has no lasting effect.", 0)
        state["details"][key] = {"room": w.room(state), "value": detail["value"]}
    person = action.get("antagonize")
    if person is not None:
        require(marks > 0 and person in w.PEOPLE and w.present(state, person) == w.room(state),
                "There is nobody there to answer.", 0)
        row = state["people"][person]
        row["trust"] = max(-2, row["trust"] - 1)
    return Attempt(text, marks)


OPERATIONS = {
    "move": walk, "take": take, "drop": drop, "place": place, "act": machine,
    "observe": observe, "lamp": handle_lamp, "supply": supply, "bind": bind, "talk": talk,
    "warn": warn, "publish": publish, "ruin": ruin, "wait": wait, "adjudicate": adjudicate,
}


def resolve(previous, action):
    """Return candidate state and perceptible results without touching disk."""
    if action.get("op") not in OPERATIONS:
        raise ValueError("Unknown operation")
    state = deepcopy(previous)
    audible = []
    refused = False
    try:
        if state["actor"]["status"] != "playing":
            raise Refusal("This playthrough has ended.", 0)
        attempt = OPERATIONS[action["op"]](state, action)
    except Refusal as blocked:
        # A failed attempt keeps its physical duration, not a partial manipulation.
        state = deepcopy(previous)
        attempt = Attempt(str(blocked), blocked.marks)
        refused = True
    until = action.get("until") if action["op"] == "wait" and not refused else None
    initially_ready = False
    if until is not None and attempt.marks:
        watched = watch(state, action)
        initially_ready = watched(state)
    for _ in range(attempt.marks):
        before_room = w.room(state)
        w.step(state, audible)
        if state["actor"]["status"] != "playing" or w.room(state) != before_room:
            break
        if until is not None:
            reached = watched(state)
            if reached and not initially_ready:
                break
            initially_ready = initially_ready and reached
    if state["actor"]["status"] == "playing":
        w.witness_surroundings(state)
    closed = None
    if w.completed(state):
        state["actor"].update(status="complete", end="return_posted")
        closed = w.ending(state)
        w.record(state, "returned", **closed)
    result = {
        "text": attempt.text, "noticed": audible, "refused": refused,
        "elapsed": state["tick"] - previous["tick"], "view": w.view(state),
    }
    if closed:
        result["ending"] = closed
    return state, result
