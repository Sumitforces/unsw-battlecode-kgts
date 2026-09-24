import random

import helper as unswbc

ct: unswbc.Controller
game: unswbc.Game

# Seeded the same way every run, so this starter bot behaves
# deterministically across languages and machines.
_rng = random.Random(0)


def _is_safe(direction: "unswbc.Direction") -> bool:
    """True if stepping this way doesn't hit kelp or another dragon."""
    here = ct.get_position()
    tile = ct.get_tile(here)
    if tile is None:
        return False

    edge = tile.get_edge(direction)
    if edge is None or not edge.is_passable():
        return False

    ahead = ct.get_tile(here.add_dir(direction))
    if ahead is None:
        # Outside our vision window — can't confirm it's clear, but it's
        # not kelp, so treat it as passable.
        return True
    return ahead.get_dragon() is None


def execute_turn() -> None:
    directions = unswbc.get_direction_list()
    _rng.shuffle(directions)
    for direction in directions:
        if _is_safe(direction):
            ct.make_move(direction)
            return
    # Nothing looked safe this turn — move anyway rather than submit no
    # action at all (which the engine treats as suicide regardless).
    ct.make_move(directions[0])


def main() -> None:
    global ct, game
    ct, game = unswbc.init()

    while unswbc.update(ct, game):
        execute_turn()
        unswbc.end_turn()


if __name__ == "__main__":
    main()
