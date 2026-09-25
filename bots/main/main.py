import helper as unswbc
from helper import Direction, EdgeType, Position
import random
from collections import deque

ct: unswbc.Controller
game: unswbc.Game

random.seed(0)

# =====================================================================
# HIVE MIND MEMORY (Persists across turns for each dragon)
# =====================================================================
MSG_TYPE_PEARL = 1
known_pearls: dict[tuple[int, int], int] = {}  # (x, y) -> round_last_seen

def encode_sonar_msg(msg_type: int, x: int, y: int) -> int:
    """Pack message type and coordinates into a 64-bit integer."""
    return (msg_type << 60) | ((x & 0x3FFFFFFF) << 30) | (y & 0x3FFFFFFF)

def decode_sonar_msg(value: int) -> tuple[int, int, int]:
    """Unpack a 64-bit integer into message type and coordinates."""
    msg_type = (value >> 60) & 0xF
    x = (value >> 30) & 0x3FFFFFFF
    y = value & 0x3FFFFFFF
    return msg_type, x, y

def wrapped_distance(pos1: Position, x2: int, y2: int, width: int, height: int) -> int:
    """Calculate shortest Manhattan distance taking map wrap-around into account."""
    dx = abs(pos1.x - x2)
    dy = abs(pos1.y - y2)
    return min(dx, width - dx) + min(dy, height - dy)

# =====================================================================
# PATHFINDING & SURVIVAL
# =====================================================================
def evaluate_space(start_pos: Position, max_depth: int) -> int:
    """
    Flood-fill to count reachable empty tiles. 
    A high max_depth ensures we NEVER walk into deep U-shaped kelp traps.
    """
    visited = {(start_pos.x, start_pos.y)}
    queue = deque([start_pos])
    space = 0
    
    while queue and space < max_depth:
        curr = queue.popleft()
        curr_tile = ct.get_tile(curr)
        
        # CRITICAL FIX: If we reach the edge of our vision, we have hit the open ocean!
        # Reward this massively (1000) so it always beats enclosed dead-ends.
        if curr_tile is None:
            space += 1000 
            continue
            
        space += 1
        for d in Direction.get_direction_list():
            edge = curr_tile.get_edge(d).get_edge_type()
            # Treat portals as solid walls to avoid blind teleports
            if edge in (EdgeType.KELP, EdgeType.PORTAL):
                continue
            
            nxt_pos = curr.add_dir(d)
            if (nxt_pos.x, nxt_pos.y) not in visited:
                nxt_tile = ct.get_tile(nxt_pos)
                if nxt_tile is None or nxt_tile.get_dragon() is None:
                    visited.add((nxt_pos.x, nxt_pos.y))
                    queue.append(nxt_pos)
                    
    return space


def find_closest_visible_pearl(start_pos: Position) -> Direction | None:
    """BFS to find the shortest path to a pearl strictly within the 7x7 vision."""
    visited = {(start_pos.x, start_pos.y)}
    queue = deque([(start_pos, [])])
    
    while queue:
        curr, path = queue.popleft()
        curr_tile = ct.get_tile(curr)
        
        if curr_tile and curr_tile.has_pearl():
            return path[0] if path else None
            
        for d in Direction.get_direction_list():
            if curr_tile is None:
                continue
                
            edge = curr_tile.get_edge(d).get_edge_type()
            if edge in (EdgeType.KELP, EdgeType.PORTAL):
                continue
                
            nxt_pos = curr.add_dir(d)
            if (nxt_pos.x, nxt_pos.y) not in visited:
                nxt_tile = ct.get_tile(nxt_pos)
                if nxt_tile is not None and nxt_tile.get_dragon() is None:
                    visited.add((nxt_pos.x, nxt_pos.y))
                    queue.append((nxt_pos, path + [d] if not path else path))
                    
    return None

# =====================================================================
# MAIN TURN LOGIC
# =====================================================================
def execute_turn() -> None:
    here = ct.get_position()
    here_tile = ct.get_tile(here)
    my_length = ct.get_length()
    round_num = game.get_round_num()
    map_w, map_h = game.get_map_size()
    
    # 1. PROCESS HIVE MIND (Update known pearls)
    for msg in ct.get_sonar_messages():
        msg_type, px, py = decode_sonar_msg(msg)
        if msg_type == MSG_TYPE_PEARL:
            known_pearls[(px, py)] = round_num

    # Update memory with what we can currently see
    for tile in ct.get_tiles():
        pos = tile.get_position()
        coord = (pos.x, pos.y)
        if tile.has_pearl():
            known_pearls[coord] = round_num
        elif coord in known_pearls:
            del known_pearls[coord]  # We see it's empty now, remove it

    # Clean stale memory (pearls reported over 40 rounds ago might be gone)
    stale = [k for k, v in known_pearls.items() if round_num - v > 40]
    for k in stale: del known_pearls[k]

    # 2. PHASE-BASED SPLITTING STRATEGY
    if ct.get_unit_count() < game.get_unit_limit():
        if round_num < 300:
            if my_length >= 5 and ct.can_split(2):
                ct.do_split(2)
                return
        elif round_num < 425:
            if my_length >= 10 and ct.can_split(3):
                ct.do_split(3)
                return

    # 3. SAFETY FIRST: Map immediately safe steps
    safe_options = []
    for d in Direction.get_direction_list():
        edge = here_tile.get_edge(d).get_edge_type()
        if edge in (EdgeType.KELP, EdgeType.PORTAL):
            continue
            
        ahead_pos = here.add_dir(d)
        ahead_tile = ct.get_tile(ahead_pos)
        if ahead_tile is not None and ahead_tile.get_dragon() is None:
            safe_options.append((d, ahead_pos))

    # 4. TRAP AVOIDANCE: Flood-fill to ensure the path doesn't lead to a dead end
    search_depth = max(my_length * 2, 16)
    scored_options = []
    for d, pos in safe_options:
        space = evaluate_space(pos, max_depth=search_depth)
        scored_options.append((space, d, pos))

    if not scored_options:
        # Absolutely trapped. Evasive fallback (just dodge kelp)
        for d in Direction.get_direction_list():
            if here_tile.get_edge(d).get_edge_type() != EdgeType.KELP:
                ct.make_move(d)
                return
        ct.make_move(Direction.NORTH)
        return

    scored_options.sort(reverse=True, key=lambda x: x[0])
    best_space = scored_options[0][0]
    
    # CRITICAL FIX: A dragon needs room to turn around without eating its own tail.
    # We require 1.5x the dragon's length in space before entering an enclosed area.
    viable_options = [opt for opt in scored_options if opt[0] == best_space or opt[0] >= (my_length * 1.5)]

    chosen_dir = None

    # 5. HUNTING PROTOCOL
    if viable_options:
        # A. Try to path to a pearl in our immediate 7x7 vision
        local_pearl_dir = find_closest_visible_pearl(here)
        if local_pearl_dir is not None:
            for space, d, pos in viable_options:
                if d == local_pearl_dir:
                    chosen_dir = d
                    break
        
        # B. If no local pearl, use Hive Mind memory to hunt distant pearls!
        if chosen_dir is None and known_pearls:
            # Find the closest known pearl from memory
            target = min(known_pearls.keys(), key=lambda p: wrapped_distance(here, p[0], p[1], map_w, map_h))
            
            # Pick the viable direction that gets us closest to the target
            best_dist = float('inf')
            for space, d, pos in viable_options:
                dist = wrapped_distance(pos, target[0], target[1], map_w, map_h)
                if dist < best_dist:
                    best_dist = dist
                    chosen_dir = d

        # C. Default: Roam safely
        if chosen_dir is None:
            best_tied_options = [opt for opt in viable_options if opt[0] == viable_options[0][0]]
            chosen_dir = random.choice(best_tied_options)[1]
    else:
        # Forced into a bad spot, take the move that buys the most time
        chosen_dir = scored_options[0][1]

    # 6. BROADCAST TO SWARM & MOVE
    # If we know of a pearl, shout its coordinates down all 4 Sonar channels
    if known_pearls:
        target_x, target_y = next(iter(known_pearls.keys()))
        msg = encode_sonar_msg(MSG_TYPE_PEARL, target_x, target_y)
        for d in Direction.get_direction_list():
            ct.send_sonar(d, msg)

    ct.make_move(chosen_dir)

def main() -> None:
    global ct, game
    ct, game = unswbc.init()

    while unswbc.update(ct, game):
        execute_turn()
        unswbc.end_turn()

if __name__ == "__main__":
    main()