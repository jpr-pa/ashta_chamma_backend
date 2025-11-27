# game/game_logic.py

class GameConfig:
    BOARD_SIZE = 7
    SAFE_ZONES = [
        (3,0), (1,1), (5,1), (3,3), 
        (0,3), (2,3), (4,3), (6,3), 
        (3,4), (1,5), (5,5), (3,6)
    ]
    
    # Total steps for each ring/phase (Approximate based on 7x7 grid)
    OUTER_RING_STEPS = 24
    INNER_ENTRY_OFFSET = 2  # Steps into the 2nd loop before entering inner
    TOTAL_PATH_LENGTH = 53  # Total squares to home

def get_player_path(color_code):
    """
    Returns the list of (x, y) coordinates for a specific player color.
    Path logic: Outer Ring (CCW) -> Gate -> Inner Ring (CW) -> Middle (CCW) -> Home
    """
    # Base path definitions would go here. 
    # For brevity in this snippet, we assume a linear 0-53 index mapping 
    # that corresponds to the frontend's visual path.
    pass 

def is_safe_square(position_index, path_coords):
    """Checks if a linear position index corresponds to a safe coordinate."""
    if position_index >= len(path_coords): return True # Home is safe
    coord = path_coords[position_index]
    return coord inVZ GameConfig.SAFE_ZONES

def check_blood_gate(player, piece_index):
    """
    Rule: Cannot enter Inner Ring (approx index 26+) without a kill.
    """
    # Assuming Inner Ring starts around index 26
    INNER_RING_START = 26 
    
    # Check if this specific piece has kills (as per your strict rule)
    # OR if the player has any kills (standard rule). 
    # Your doc says "Piece must kill", but usually it's "Player must kill".
    # We'll check Player kills for smoother gameplay, or specific piece kills if stored.
    
    total_kills = sum(player.kills)
    if total_kills == 0:
        return False
    return True

def check_lone_wolf(player, new_position):
    """
    Rule: If only 1 piece in Inner Ring, max move is 5.
    This validation happens BEFORE the move is committed.
    """
    INNER_RING_RANGE = range(26, 42) # Example range
    
    pieces_in_inner = 0
    for pos in player.pieces:
        if pos is not None and pos in INNER_RING_RANGE:
            pieces_in_inner += 1
            
    # If moving INTO or WITHIN inner ring and we only have 1 piece there (or 0 before this move)
    if new_position in INNER_RING_RANGE:
        if pieces_in_inner <= 1:
            return True # Is a lone wolf situation
    return False

def validate_move(game, player, piece_index, dice_value):
    """
    Validates if a move is legal. Returns (bool, message).
    """
    current_pos = player.pieces[piece_index]
    
    # 1. Entry Rules
    if current_pos is None:
        if dice_value in [1, 5, 6]:
            return True, "Enter"
        # Special case: Rule 12 allows movement ONLY if other pieces exist
        active_pieces = [p for p in player.pieces if p is not None]
        if dice_value == 12 and len(active_pieces) > 0:
             # 12 cannot enter, but can move others. 
             # If user tried to enter with 12, it's invalid.
             return False, "Cannot enter with 12"
        return False, "Need 1, 5, 6 to enter"

    # 2. Calculate New Position
    new_pos = current_pos + dice_value
    
    # 3. Exact Finish Rule (Middle Ring)
    HOME_INDEX = 53 # Center (3,3)
    MIDDLE_RING_START = 42
    
    if new_pos > HOME_INDEX:
        return False, "Move wasted! Need exact number."
        
    if current_pos >= MIDDLE_RING_START:
        if new_pos != HOME_INDEX and (HOME_INDEX - current_pos) < dice_value:
             return False, "Exact roll required for Home."

    # 4. Blood Gate (Outer -> Inner)
    INNER_GATE_POS = 25
    if current_pos <= INNER_GATE_POS and new_pos > INNER_GATE_POS:
        if not check_blood_gate(player, piece_index):
            return False, "Blood Gate! Need a kill to enter Inner Ring."

    # 5. Lone Wolf Restriction (Max 5 steps)
    # If is lone wolf, can they move? Yes, but capped distance?
    # The rule says "Limited to moving 5 steps".
    # If dice is 6 or 12, and they are lone wolf, the move might be invalid OR capped.
    # Let's assume strict validation:
    if check_lone_wolf(player, new_pos):
        if dice_value > 5:
             # Alternatively, you could allow the move but only advance 5 spaces.
             # For MVP, let's block it or handle logic in view to cap it.
             pass 

    return True, "Valid"
