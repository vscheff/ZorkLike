# Simulation and command reference

Engine material. Commands below are representations used by Codex after parsing intent. They are never input requirements for the player.

## Time and perception

- Marks are global to an individual run. Anything the runner leaves in motion continues offscreen. Real time between messages has no effect.
- Movement, manipulation, local conversation and unsuccessful physical attempts ordinarily take one mark. The Long Span takes two. Adjusting both parts of the selector takes two. Taking time to do a physical task is different from naming something unreachable or failing to clarify a referent. Look, inventory, examination, reading and administrative commands cost zero. Record discoveries even when their actions cost zero.
- At the beginning of the action, use current local conditions to resolve the immediate manipulation. For each mark, advance the bell, people, flame, drives, warnings, live transfer and local hazards in that order. An observable action may precede something the following pulse changes. Any action that displaces the runner during a wait interrupts that wait at the consequence. Death ends the action and the playthrough. Victory is checked only after the last mark of the return.
- Phase repeats every twelve marks. Levels at phases 0 through 11 are 0, 0, 0, 1, 2, 3, 3, 3, 2, 1, 0, 0. Below second black means level 0 or 1. Treat general high water as levels 2 and 3. The current mark is directly readable in the bell count when nearby, or elapsed marks in STATUS. Display a gauge only when it can be read or interpreted in character. Exit obstructions are adjudication data. A bare look can report closed metal or flowing water, rather than describing a manipulation the runner hasn't done.
- Wash Step, Culvert Mouth and Sluice Shelf are exposed. Footways are usable at 0–1. Enter and leave in one mark each. Remaining into a rise to 2 sweeps the runner onto the mapped lee apron with one injury. Loose objects there are swept off; a lamp or exposed recorder leaf in hand is ruined. At 3 the same cuts are wholly submerged and anyone committed to the water dies. The rising current shows itself before these actions, and guard signs say where it will go. A closed water route cannot be opened by an instruction that simply assumes success. A deliberate plunge into a known route at high water uses `force` and takes the local consequence immediately.
- Three points of health are intact, two hurt, one badly hurt, zero dead. The sole linen binding can restore one point after a real injury. No automatic healing or recall on death. Learn character names in conversation, from a known introduction, or a visible personal label. Show only objects physically present and perceptible, including installed parts if the runner can reach them. In darkness a known turn, a lighted neighboring area, or a careful tactile search can make progress. Do not offer the map. Lights in the lower inhabited rooms are fixed household fixtures.
- The tin lamp holds 18 marks of oil, including the mark of lighting. It continues burning if set down. Its own striker works by touch. The stoppered tin starts with 12 marks and the oil stand fills it to 24. Refilling requires a cold, accessible lamp and tin in hand. Supplies cannot reappear after irreversible loss.
- Carry at most 12 bulk. Bulk is space and handling difficulty. The hatch scale measures load divisions, which are separate. Reach methods and support must make physical sense from the room. A heavy thing is never mysteriously immune to throwing or loss.

## Drives and structural effects

- The service hatch opens from above while its pan bears six divisions or more, or while the raised catch is properly propped. Weight placed on the room floor doesn't reach the pan. The latch slips directly from below. A fixed six-division iron weight is one solution. Pieces with combined weight and available space in the pan work as well. Installing either valid drive retainer catches both cradle lugs. Calls take three marks including the call. Board or leave a stationary car only at its respective stop. The old inlet connects a separately dry passage to the exposed shelf after the grill is lifted.
- The recorder takes three marks including the starting stroke. Current head and all three pulse levels must stay below second black for a dry print. Remove the leaf early to cancel. Content changes on an intact leaf; former readable impressions are remembered facts and don't move with its new reading. The three loops and the living proof are physically distinct, as detailed in canon.
- A sealed open east feeder gains one bead per mark at second black or higher. It retains the charge while open. A shut valve bleeds one at slack as long as the seat has not taken. A seated jack retains all three. Pulling the seal unseats an idle bed. The west test reads head at its start. Forcing the wheel under high head against HOLD fails the shoe and heel permanently. Once actually under load the vents and packs hold under the mechanism's own pressure.
- The final train strikes three pulses including engage. The old link holds while the train advances. Starting above first black meets hard pressure. High head or missing receiver support in a live train, forcing the lever through high pressure, or prematurely pulling the old dog collapses the old line. The black stop halts a live train immediately while the old dog still holds. Failure leaves genuine consequences, can kill the runner in a risk room, and blocks routes into the structural footprint. See VICTORY.md for the complete predicate.
- Warnings name the destination and require observable evidence or the proper writ and a person actually present. Orchard and shore warnings take four marks; a lower warning takes six with the grille open. The lower response follows a physical route, one passage per mark. Shutting that grille before clearance delays the warning. Established residents and specific tools are saved only by actual movement or the prescribed response. Warning does not change where water flows.
- Graft stock in the original Seed Loft spoils on an east spill. Leaving the seed box on the designated dry shelf preserves it for immediate use. A box somewhere else survives if that place or object remained safe. The order and ferry sheet are two genuine documentary alternatives. Posting retains a public copy of what was seen even if the portable original is later reclaimed.
- Tick, geometry, machinery, behavior and the outcomes in this design are deterministic. No rolls are required. Where the fiction implies an ordinary small uncertainty, resolve by access and material conditions; no narrative rerolls. Rare future random extensions require a declared model and recorded result before use, and cannot change the canonical critical path.

## Operation keys

Common fields are `op`, with `item`, `target`, `setting` or `person` as applicable. Use stable keys from WORLD.json and the room notes.

| Operation | Fields and intent |
| --- | --- |
| `move` | `direction` is n, s, e, w, ne, nw, se, sw, u or d. `feel: true` when actually feeling ahead in unfamiliar dark. `force: true` only for an explicit deliberate plunge on an exposed route. |
| `take` / `drop` | `item`; taking by feel needs a previously known thing. Placing explicitly on an available ordinary surface can be a drop in the room with a local detail if position matters. |
| `place` | `item`, `target` from hatch_pan, hatch_taper, drive_socket, scratch_frame, east_packing, west_socket. A reachable loose object in the same room may be placed directly. |
| `observe` | Optional `target` for a readable or perceptible fixture/object, `method` from examine/read/search/listen/feel, and a local `fact` from the discoveries in actions.py. With no named target can record a specific scene fact established in the room. Use for knowledge only when actually discovered. |
| `lamp` | `setting` light, snuff or refill. |
| `supply` | `item` oil_tin or rag, operating the stand in the Oil Room. |
| `bind` | Apply the clean linen to a current injury. |
| `talk` | `person`, optional `topic` as listed in the dialogue table. Showing Mera the delivery slip uses topic slip. Showing Nemi the fare counter uses topic counter. Sile can operate the press if present as a rendition of the same filing action. |
| `warn` | `person` van, iss or mera. |
| `publish` | `item` ferry_list or rent_carbon, posting to the meeting board. |
| `ruin` | `item` and `method` smash, tear or throw when material and site support it. Committed loss persists. Turn the typed action into a physically meaningful attempt, including when it fails. |
| `wait` | `marks` from 1 to 48. Optional `until` low, high, cradle, draw, transfer, east_full or person, whence `person` identifies someone the runner can recognize. Use only local observable conditions; `next: true` waits for another occurrence. For longer explicit waits, use additional blocks only if the character has chosen that much time and can still wait. |
| `adjudicate` | `marks` 0–4, a short observable `text`, optional `detail: {"id":"stable_ID","value":...}` for a small local change or observed fact, or `antagonize: "person_ID"` for intentional outward hostility to a physically present person. Never use this for untracked structural changes. |

For `{"op":"act","kind":"..."}`, the primary kinds are below. Position, equipment, timing and state are validated by the resolver.

| Kind | Additional fields |
| --- | --- |
| call_cradle | setting up/down |
| open_inlet, open_loft, get_loft | item, the carried implement used to reach. Setting shut reverses the inlet or boards. |
| open_ferry, open_stack, pry_docket, open_foil, press_foil | Use the authored local operation and its required tools. |
| open_root | Set shut to close from either side after opening. Default opens from uphill_gap below. |
| recorder_loop | setting 11, 19 or 27 as a number |
| draw | Start or replace the draw on the mounted leaf. |
| file_claim | item witness_strip or spare_foil, with recorder leaf also held |
| admit_writ | At any lock approach, writ in hand. |
| east_valve | setting open/shut |
| east_seat, west_test | Test the locally prepared receiver. west_test can force hard resistance if the runner explicitly attempts it. |
| west_vent | setting hold/river |
| select | loop 11/19/27, bed east/west, or both when explicitly attempted |
| engage, stop, release_dog | Operate the respective levers locally. Engage accepts force for an explicit attempt against hard pressure. |
| post_return | Lodge the band at its socket. |

Resolve meaningful verb variants to their local action. A manipulation with a valid unanticipated manner can use the same effect if it satisfies that effect's physical preconditions. Give the reason observable at the point of failure. Leave irreversible choices and the next step to the player.
