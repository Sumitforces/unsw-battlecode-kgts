"""
helper.py — wire-protocol I/O layer for a Battlecode sea-dragon bot.

Implements protocol version 3 (directed 64-bit sonar + echoes) as
documented at https://game.battlecode.au/docs/protocol. Reads the
engine's plain-text stdin, writes the reply commands to stdout, and
exposes the same object model as the toolkit's own helper
(Direction, Position, Tile, Edge, DragonPart, Vision, SonarEchoes,
Game, Controller) so a bot can be written against this file exactly
like the stock one.

This file has no strategy in it — it is purely the protocol layer.
Edit main.py, not this file, unless you need to change how a turn is
read or written.
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# stdin helpers
# --------------------------------------------------------------------------

def _read_line() -> Optional[str]:
    """Read one non-blank, comment-stripped line from stdin, or None at EOF."""
    while True:
        raw = sys.stdin.readline()
        if raw == "":
            return None
        line = raw.split("#", 1)[0].strip()
        if line:
            return line


# --------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------

class Direction:
    """One of the four cardinal directions. North is up; y grows downward."""

    __slots__ = ("_letter", "_dx", "_dy", "_name")

    def __init__(self, name: str, letter: str, dx: int, dy: int):
        self._name = name
        self._letter = letter
        self._dx = dx
        self._dy = dy

    def value(self) -> str:
        """The protocol letter: N, E, S or W."""
        return self._letter

    def get_offset(self) -> Tuple[int, int]:
        """(dx, dy) of one step this way, with y growing downwards."""
        return (self._dx, self._dy)

    def get_opposite(self) -> "Direction":
        return _OPPOSITE[self]

    def get_left(self) -> "Direction":
        """A quarter turn anticlockwise."""
        return _LEFT[self]

    def get_right(self) -> "Direction":
        """A quarter turn clockwise."""
        return _RIGHT[self]

    @staticmethod
    def get_direction_list() -> List["Direction"]:
        """A fresh list of all four: north, east, south, west."""
        return [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

    def __repr__(self) -> str:
        return f"Direction.{self._name}"


Direction.NORTH = Direction("NORTH", "N", 0, -1)
Direction.EAST = Direction("EAST", "E", 1, 0)
Direction.SOUTH = Direction("SOUTH", "S", 0, 1)
Direction.WEST = Direction("WEST", "W", -1, 0)

_OPPOSITE = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}
_LEFT = {
    Direction.NORTH: Direction.WEST,
    Direction.WEST: Direction.SOUTH,
    Direction.SOUTH: Direction.EAST,
    Direction.EAST: Direction.NORTH,
}
_RIGHT = {
    Direction.NORTH: Direction.EAST,
    Direction.EAST: Direction.SOUTH,
    Direction.SOUTH: Direction.WEST,
    Direction.WEST: Direction.NORTH,
}
_LETTER_TO_DIRECTION = {d.value(): d for d in Direction.get_direction_list()}


def get_direction_list() -> List[Direction]:
    """Module-level alias of Direction.get_direction_list()."""
    return Direction.get_direction_list()


# --------------------------------------------------------------------------
# Team
# --------------------------------------------------------------------------

class Team:
    __slots__ = ("_name",)

    def __init__(self, name: str):
        self._name = name

    def get_enemy_team(self) -> "Team":
        return Team.B if self is Team.A else Team.A

    def __repr__(self) -> str:
        return f"Team.{self._name}"


Team.A = Team("A")
Team.B = Team("B")
_LETTER_TO_TEAM = {"A": Team.A, "B": Team.B}


# --------------------------------------------------------------------------
# Global state needed by Position (map size, current head, for
# is_in_map()/is_in_vision()) — updated every update() call.
# --------------------------------------------------------------------------

class _GameState:
    def __init__(self):
        self.map_size: Tuple[int, int] = (0, 0)
        self.head_position: Optional["Position"] = None


_STATE = _GameState()


# --------------------------------------------------------------------------
# Position
# --------------------------------------------------------------------------

class Position:
    """A tile's x, y. (0, 0) is top-left; y grows downward."""

    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def add_dir(self, direction: Direction) -> "Position":
        """The position one step that way, wrapped around the map edges."""
        dx, dy = direction.get_offset()
        w, h = _STATE.map_size
        nx = (self.x + dx) % w if w else self.x + dx
        ny = (self.y + dy) % h if h else self.y + dy
        return Position(nx, ny)

    def is_in_map(self) -> bool:
        w, h = _STATE.map_size
        return 0 <= self.x < w and 0 <= self.y < h

    def is_in_vision(self) -> bool:
        """Whether this tile is inside the current head's 7x7 window."""
        head = _STATE.head_position
        if head is None:
            return False
        w, h = _STATE.map_size
        dx = abs(self.x - head.x)
        dx = min(dx, w - dx) if w else dx
        dy = abs(self.y - head.y)
        dy = min(dy, h - dy) if h else dy
        return dx <= 3 and dy <= 3

    def __eq__(self, other) -> bool:
        return isinstance(other, Position) and self.x == other.x and self.y == other.y

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __repr__(self) -> str:
        return f"Position({self.x}, {self.y})"


# --------------------------------------------------------------------------
# EdgeType / Edge
# --------------------------------------------------------------------------

class EdgeType:
    __slots__ = ("_name",)

    def __init__(self, name: str):
        self._name = name

    def __repr__(self) -> str:
        return f"EdgeType.{self._name}"


EdgeType.EMPTY = EdgeType("EMPTY")
EdgeType.KELP = EdgeType("KELP")
EdgeType.PORTAL = EdgeType("PORTAL")


class Edge:
    """The boundary between two tiles."""

    __slots__ = ("_type", "_portal_id")

    def __init__(self, edge_type: EdgeType, portal_id: int = -1):
        self._type = edge_type
        self._portal_id = portal_id

    def is_passable(self) -> bool:
        return self._type is not EdgeType.KELP

    def is_portal(self) -> bool:
        return self._type is EdgeType.PORTAL

    def get_edge_type(self) -> EdgeType:
        return self._type

    def get_portal_id(self) -> int:
        return self._portal_id


def _parse_edge(symbol: str) -> Edge:
    if symbol == ".":
        return Edge(EdgeType.EMPTY)
    if symbol == "w":
        return Edge(EdgeType.KELP)
    return Edge(EdgeType.PORTAL, int(symbol))


# --------------------------------------------------------------------------
# DragonPart
# --------------------------------------------------------------------------

class DragonPart:
    """One segment of a dragon, head or body."""

    __slots__ = ("_team", "_id", "_position", "_dir", "_is_head")

    def __init__(self, team: Team, dragon_id: int, position: Position,
                 direction: Direction, is_head: bool):
        self._team = team
        self._id = dragon_id
        self._position = position
        self._dir = direction
        self._is_head = is_head

    def get_position(self) -> Position:
        return self._position

    def get_id(self) -> int:
        return self._id

    def get_team(self) -> Team:
        return self._team

    def get_dir(self) -> Direction:
        return self._dir

    def is_head(self) -> bool:
        return self._is_head


# --------------------------------------------------------------------------
# Tile
# --------------------------------------------------------------------------

class Tile:
    """One square of the board, with whatever stands on it and its edges."""

    __slots__ = ("_position", "_has_pearl", "_pearl_time", "_dragon", "_edges")

    def __init__(self, position: Position, has_pearl: bool, pearl_time: int):
        self._position = position
        self._has_pearl = has_pearl
        self._pearl_time = pearl_time
        self._dragon: Optional[DragonPart] = None
        self._edges: Dict[Direction, Edge] = {}

    def edges(self) -> Dict[Direction, Edge]:
        return dict(self._edges)

    def get_edge(self, direction: Direction) -> Optional[Edge]:
        return self._edges.get(direction)

    def get_dragon(self) -> Optional[DragonPart]:
        return self._dragon

    def has_pearl(self) -> bool:
        return self._has_pearl

    def get_pearl_time(self) -> int:
        """Rounds until this tile next spawns a pearl, or -1 if it never does."""
        return self._pearl_time

    def get_position(self) -> Position:
        return self._position


# --------------------------------------------------------------------------
# Vision
# --------------------------------------------------------------------------

class Vision:
    """The 7x7 block of tiles around a dragon's head."""

    __slots__ = ("_by_pos", "_ordered")

    def __init__(self, by_pos: Dict[Tuple[int, int], Tile], ordered: List[Tile]):
        self._by_pos = by_pos
        self._ordered = ordered

    def get_tiles(self) -> List[Tile]:
        """All 49 tiles, row by row from the top left of the window."""
        return list(self._ordered)

    def get_tile(self, pos: Position) -> Optional[Tile]:
        return self._by_pos.get((pos.x, pos.y))


# --------------------------------------------------------------------------
# SonarEchoes
# --------------------------------------------------------------------------

class SonarEchoes:
    """Counts of what each of a dragon's sonars stopped on last turn."""

    __slots__ = ("kelp", "ally", "ally_head", "enemy", "enemy_head")

    def __init__(self, kelp: int, ally: int, ally_head: int, enemy: int, enemy_head: int):
        self.kelp = kelp
        self.ally = ally
        self.ally_head = ally_head
        self.enemy = enemy
        self.enemy_head = enemy_head

    def __repr__(self) -> str:
        return (f"SonarEchoes(kelp={self.kelp}, ally={self.ally}, "
                f"ally_head={self.ally_head}, enemy={self.enemy}, "
                f"enemy_head={self.enemy_head})")


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------

class Game:
    """The board and the round number, shared by every dragon."""

    __slots__ = ("_round_num", "_map_size", "_unit_limit")

    def __init__(self):
        self._round_num = 0
        self._map_size = (0, 0)
        self._unit_limit = 64

    def get_round_num(self) -> int:
        return self._round_num

    def get_map_size(self) -> Tuple[int, int]:
        return self._map_size

    def get_unit_limit(self) -> int:
        return self._unit_limit


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------

class Controller:
    """Your dragon: what it sees, how long it is, and this turn's commands."""

    def __init__(self, dragon_id: int, team: Team, unit_limit: int):
        self.id = dragon_id
        self.team = team
        self.dir = Direction.NORTH
        self.length = 0
        self.unit_count = 0
        self.position = Position(0, 0)
        self.vision: Optional[Vision] = None

        self._unit_limit = unit_limit
        self._sonar_messages: List[int] = []
        self._sonar_echoes = SonarEchoes(0, 0, 0, 0, 0)

        # this turn's pending reply, flushed by end_turn()
        self._pending_action: Optional[Tuple[str, object]] = None
        self._pending_sonar: Dict[Direction, int] = {}
        self._pending_indicator: Optional[str] = None
        self._immediate_lines: List[str] = []

    # -- called by update(), not by bot code --------------------------

    def _apply_round(self, direction: Direction, length: int, unit_count: int,
                      sonar_messages: List[int], sonar_echoes: SonarEchoes,
                      vision: Vision, position: Position) -> None:
        self.dir = direction
        self.length = length
        self.unit_count = unit_count
        self._sonar_messages = sonar_messages
        self._sonar_echoes = sonar_echoes
        self.vision = vision
        self.position = position

        self._pending_action = None
        self._pending_sonar = {}
        self._pending_indicator = None
        self._immediate_lines = []

    # -- queries --------------------------------------------------------

    def get_length(self) -> int:
        return self.length

    def get_unit_count(self) -> int:
        return self.unit_count

    def get_head(self) -> DragonPart:
        tile = self.vision.get_tile(self.position) if self.vision else None
        if tile is not None:
            part = tile.get_dragon()
            if part is not None and part.get_id() == self.id:
                return part
        # Shouldn't happen — the head is always in its own vision — but
        # fall back to a synthetic part rather than raising.
        return DragonPart(self.team, self.id, self.position, self.dir, True)

    def get_id(self) -> int:
        return self.id

    def get_team(self) -> Team:
        return self.team

    def get_dir(self) -> Direction:
        return self.dir

    def get_vision(self) -> Optional[Vision]:
        return self.vision

    def get_tiles(self) -> List[Tile]:
        return self.vision.get_tiles() if self.vision else []

    def get_tile(self, pos: Position) -> Optional[Tile]:
        return self.vision.get_tile(pos) if self.vision else None

    def get_position(self) -> Position:
        return self.position

    # -- actions (only the last one read is applied) --------------------

    def make_move(self, direction: Direction) -> None:
        """Steps one tile that way."""
        self._pending_action = ("MOVE", [direction])

    def make_moves(self, directions: List[Direction]) -> None:
        """Sprints one step per direction in the list."""
        self._pending_action = ("MOVE", list(directions))

    def can_split(self, child_size: int) -> bool:
        """Whether a child of that many segments is legal this turn."""
        if child_size < 2:
            return False
        if self.length - child_size < 2:
            return False
        if self.unit_count >= self._unit_limit:
            return False
        return True

    def do_split(self, child_size: int) -> None:
        """Splits that many segments off your tail."""
        self._pending_action = ("SPLIT", child_size)

    # -- sonar ------------------------------------------------------------

    def get_sonar_messages(self) -> List[int]:
        """Values that reached you since your last turn, in send order."""
        return list(self._sonar_messages)

    def get_sonar_echoes(self) -> SonarEchoes:
        return self._sonar_echoes

    def send_sonar(self, direction_or_message, message: Optional[int] = None) -> bool:
        """
        send_sonar(direction, value) pings that way after this turn's action.
        send_sonar(value) (no direction) is the protocol-2 form: it pings in
        your current facing direction.
        """
        if message is None:
            direction = self.dir
            value = direction_or_message
        else:
            direction = direction_or_message
            value = message
        self._pending_sonar[direction] = value
        return True

    # -- drawing / logging (applied immediately, in call order) ---------

    def output_log(self, *message) -> None:
        text = " ".join(str(m) for m in message)
        self._immediate_lines.append(f"LOG {text}")

    def draw_indicator_dot(self, pos: Position, r: int, g: int, b: int) -> None:
        self._immediate_lines.append(f"DOT {pos.x} {pos.y} {r} {g} {b}")

    def draw_indicator_line(self, start: Position, end: Position,
                             r: int, g: int, b: int) -> None:
        self._immediate_lines.append(
            f"LINE {start.x} {start.y} {end.x} {end.y} {r} {g} {b}"
        )

    def set_indicator_string(self, message: str) -> None:
        self._pending_indicator = message


# --------------------------------------------------------------------------
# module-level game loop: init() / update() / end_turn()
# --------------------------------------------------------------------------

_controller: Optional[Controller] = None


def init() -> Tuple[Controller, Game]:
    """Reads the init block and returns (controller, game), valid all match."""
    global _controller

    fields: Dict[str, object] = {}
    while len(fields) < 4:
        line = _read_line()
        if line is None:
            sys.exit(0)
        parts = line.split()
        key = parts[0]
        if key == "ID":
            fields["ID"] = int(parts[1])
        elif key == "TEAM":
            fields["TEAM"] = parts[1]
        elif key == "MAP":
            fields["MAP"] = (int(parts[1]), int(parts[2]))
        elif key == "UNIT_LIMIT":
            fields["UNIT_LIMIT"] = int(parts[1])

    game = Game()
    game._map_size = fields["MAP"]
    game._unit_limit = fields["UNIT_LIMIT"]

    team = _LETTER_TO_TEAM[fields["TEAM"]]
    controller = Controller(fields["ID"], team, game._unit_limit)

    _STATE.map_size = game._map_size
    _controller = controller

    return controller, game


def update(controller: Controller, game: Game) -> bool:
    """
    Reads the next turn into the controller. Returns False once the game
    is over or this dragon has died (stdin hit EOF).
    """
    global _controller
    _controller = controller

    line = _read_line()
    if line is None:
        return False
    parts = line.split()
    round_num = int(parts[1])  # ROUND <n>

    line = _read_line()
    dir_letter = line.split()[1]  # DIR <letter>

    line = _read_line()
    length = int(line.split()[1])  # LENGTH <n>

    line = _read_line()
    unit_count = int(line.split()[1])  # UNIT_COUNT <n>

    line = _read_line()
    num_msgs = int(line.split()[1])  # NUM_MSGS <n>
    sonar_messages = [int(_read_line()) for _ in range(num_msgs)]

    line = _read_line()
    echo_parts = line.split()  # ECHOES k a ah e eh
    sonar_echoes = SonarEchoes(*(int(v) for v in echo_parts[1:6]))

    # 49 tile lines, row by row (row 0 = 3 north of head, col 0 = 3 west)
    grid: List[List[Tile]] = []
    ordered: List[Tile] = []
    by_pos: Dict[Tuple[int, int], Tile] = {}
    for _row in range(7):
        row_tiles: List[Tile] = []
        for _col in range(7):
            tx, ty, has_pearl, pearl_in = _read_line().split()
            tile = Tile(Position(int(tx), int(ty)), has_pearl == "1", int(pearl_in))
            row_tiles.append(tile)
            ordered.append(tile)
            by_pos[(tile.get_position().x, tile.get_position().y)] = tile
        grid.append(row_tiles)

    # dragon bodies inside the window
    line = _read_line()
    n_bodies = int(line.split()[1])  # DRAGON_BODIES <n>
    own_head_pos: Optional[Position] = None
    for _ in range(n_bodies):
        team_letter, id_str, x, y, facing, is_head = _read_line().split()
        pos = Position(int(x), int(y))
        part = DragonPart(
            _LETTER_TO_TEAM[team_letter],
            int(id_str),
            pos,
            _LETTER_TO_DIRECTION[facing],
            is_head == "1",
        )
        tile = by_pos.get((pos.x, pos.y))
        if tile is not None:
            tile._dragon = part
        if part.is_head() and part.get_id() == controller.id:
            own_head_pos = pos

    # horizontal edges: 8 lines of 7 (north of each row, then south of last row)
    horiz = [_read_line().split() for _ in range(8)]
    # vertical edges: 7 lines of 8 (west of each column, then east of last column)
    vert = [_read_line().split() for _ in range(7)]

    for row in range(7):
        for col in range(7):
            tile = grid[row][col]
            tile._edges[Direction.NORTH] = _parse_edge(horiz[row][col])
            tile._edges[Direction.SOUTH] = _parse_edge(horiz[row + 1][col])
            tile._edges[Direction.WEST] = _parse_edge(vert[row][col])
            tile._edges[Direction.EAST] = _parse_edge(vert[row][col + 1])

    vision = Vision(by_pos, ordered)

    game._round_num = round_num
    controller._apply_round(
        direction=_LETTER_TO_DIRECTION[dir_letter],
        length=length,
        unit_count=unit_count,
        sonar_messages=sonar_messages,
        sonar_echoes=sonar_echoes,
        vision=vision,
        position=own_head_pos if own_head_pos is not None else controller.position,
    )

    _STATE.map_size = game._map_size
    _STATE.head_position = controller.position

    return True


def end_turn() -> None:
    """Ends the turn: writes the reply and flushes stdout."""
    c = _controller
    if c is None:
        return

    lines: List[str] = list(c._immediate_lines)

    if c._pending_indicator is not None:
        lines.append(f"INDICATOR {c._pending_indicator}")

    for direction in Direction.get_direction_list():
        if direction in c._pending_sonar:
            lines.append(f"SONAR {direction.value()} {c._pending_sonar[direction]}")

    if c._pending_action is not None:
        kind, payload = c._pending_action
        if kind == "MOVE":
            letters = "".join(d.value() for d in payload)
            lines.append(f"MOVE {letters}")
        elif kind == "SPLIT":
            lines.append(f"SPLIT {payload}")

    # Ask for protocol 3 from the start so 64-bit sonar and echoes work.
    lines.append("PROTOCOL 3")
    lines.append("ENDTURN")

    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()
