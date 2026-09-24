# unsw-battlecode-kgts


--> checkout readme2 for details if you wanna edit the idea, or implment an idea. 
--> thats it.

Team repo for UNSW Battlecode (the "sea dragons" game). This holds the
toolkit project layout for our submissions — no strategy in here yet,
just the boilerplate needed to build, test and submit a bot.

## Layout

```
unsw-battlecode-kgts/
├── bots/
│   └── main/            # our active bot project (unswbc project dir)
│       ├── bot.toml     # submission config (language + files to ship)
│       ├── main.py      # bot logic — edit execute_turn() here
│       └── helper.py    # wire-protocol I/O layer (parses stdin, writes stdout)
├── maps/                # shared maps, populated by `unswbc maps`
└── README.md
```

`bots/main` is a normal `unswbc init python` project; `helper.py` is a
from-scratch implementation of the documented wire protocol (v3, with
directed 64-bit sonar + echoes), in case we ever need to diverge from
the toolkit's own helper.

## One-time setup

```bash
# install the toolkit (uv recommended)
uv tool install unswbc
# or: pip install unswbc

# sanity check: interpreter, compilers, replay viewer
unswbc

# pull the bundled maps into maps/
unswbc maps maps

# store your team API key (from https://game.battlecode.au/team)
unswbc auth set bc_...
unswbc auth status
```

## Running a match

```bash
unswbc run maps/arena.map bots/main bots/main
```

Add `-v` to watch every round, or `--sandbox` to run it priced in CPU
points exactly as the judge does (see the Timeouts doc).

Open the `.replay` file it writes — the VS Code / Cursor / VSCodium
extension (`unswbc vscode`) opens it directly, or use
https://game.battlecode.au/visualiser.

## Submitting

```bash
unswbc submit bots/main -n v1 -d "initial boilerplate"
```

One build is active at a time; `unswbc submit` uploads a new version,
and activation happens automatically once it builds (or from
Submissions on the site).

## Docs

- Rules: https://game.battlecode.au/docs/overview
- CLI reference: https://game.battlecode.au/docs/cli
- Wire protocol: https://game.battlecode.au/docs/protocol
- API (submissions/battles over HTTP): https://game.battlecode.au/docs/api
