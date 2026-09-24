# README2 — where strategy code goes

This is the map of the codebase for when we start cooking up actual
play. Short version: **almost everything you write goes in
`bots/main/main.py`. Don't touch `helper.py` unless the protocol
itself is wrong.**

## Edit this: `bots/main/main.py`

This is the only file strategy lives in.

- `execute_turn()` — called once per living dragon, per turn. Every
  decision (where to move, when to split, what to sonar) happens by
  calling methods on `ct` (the `Controller`) from inside here, or
  from functions you add and call from here.
- Anything above `execute_turn()` — module-level constants, helper
  functions (`_is_safe`, pathing, target selection, sonar-message
  encoding/decoding, etc.) — add as many of these as you like. The
  starter bot's `_is_safe` is a placeholder; replace or extend it.
- `main()` — the game loop. Leave this alone. It's just
  `init()` → `while update(): execute_turn(); end_turn()`, per the
  documented template. There's no reason to change it.
- `_rng` — currently seeded (`random.Random(0)`) so the starter bot
  is deterministic. Keep it seeded, or reseed per-dragon from
  `ct.get_id()`, if you want dragons to act differently from each
  other; don't switch to unseeded `random` — replays wouldn't be
  reproducible for debugging.

Read from `ct` (see the full list in `helper.py`'s `Controller`
class, or the [Helper reference](https://game.battlecode.au/docs/helper-reference)):
`get_position()`, `get_tile()` / `get_tiles()`, `get_length()`,
`get_dir()`, `get_sonar_messages()`, `get_sonar_echoes()`, etc.

Write to `ct` to act: `make_move()`, `make_moves()`, `do_split()`,
`send_sonar()`, plus the non-gameplay ones —
`set_indicator_string()`, `output_log()`, `draw_indicator_dot()`,
`draw_indicator_line()` — for debugging in the replay viewer.

Remember the constraints while you're deciding what to do in
`execute_turn()`:
- Only your **last** `make_move`/`make_moves`/`do_split` call counts
  — the rest are silently overwritten. Same for `send_sonar()` per
  direction, and for `set_indicator_string()`.
- Every dragon runs its own copy of this file with no shared memory.
  Cross-dragon communication only happens through `send_sonar()` /
  `get_sonar_messages()` — see [Sonar](https://game.battlecode.au/docs/sonar).
- ~25ms / 100M CPU points per dragon per turn. Heavy precompute
  should be spread across turns or made lazy — see
  [Timeouts](https://game.battlecode.au/docs/timeouts).

## Leave this alone: `bots/main/helper.py`

This is the protocol layer — it reads the engine's stdin and writes
our stdout. It has no game logic in it, so there's nothing here for
a strategy change to touch. Only edit it if:

- We find a parsing bug (mismatched field count, wrong edge mapping,
  etc.) against the actual [wire protocol](https://game.battlecode.au/docs/protocol).
- We want to add a convenience method to `Controller`/`Tile`/etc.
  that's still pure plumbing (e.g. a `Tile.neighbours()` helper) —
  fine to add here, but keep it free of strategy decisions.
- We upgrade to a future protocol version.

If you're tempted to add something stateful that persists across
turns (a remembered map, a role assignment, a plan), that's still a
`main.py` concern — store it in a module-level dict/variable in
`main.py`, not in `helper.py`'s `Controller`.

## Leave this alone: `bots/main/bot.toml`

Only touch this if we add new source files that need shipping (add
them to `include`) or split the bot into multiple modules
(`main.py` importing a `strategy.py` you add — just remember to add
`strategy.py` to `include` too, since `bot.toml` controls what's
zipped for submission).

## Multiple strategies / experiments

If we want to try more than one approach side by side:

```
bots/
├── main/        # the one we submit — unswbc submit bots/main
├── rusher/       # experiment
└── farmer/       # experiment
```

Each is a full copy of `bot.toml` + `main.py` + `helper.py` (copy
`helper.py` verbatim, don't fork it per experiment). Play them
against each other locally:

```bash
unswbc run maps/arena.map bots/rusher bots/farmer
```

Only `bots/main` (or whichever wins) gets `unswbc submit`'d.
