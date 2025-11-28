# game/game_logic.py

class GameConfig:
    # 7x7 Board Configuration
    SAFE_ZONES = [
        (3,0), (1,1), (5,1), (3,3), 
        (0,3), (2,3), (4,3), (6,3), 
        (3,4), (1,5), (5,5), (3,6)
    ]
    HOME_INDEX = 53  # The final step index to reach home

def check_blood_gate(player, piece_index):
    """Rule: Cannot enter Inner Ring without a kill."""
    # Assuming Inner Ring starts after the first loop (approx step 25)
    INNER_RING_GATE = 25
    
    # Check total kills for the player
    total_kills = sum(player.kills)
    if total_kills == 0:
        return False
    return True

def check_lone_wolf(player, new_position):
    """Rule: If only 1 piece in Inner Ring, max move is 5."""
    # Define Inner Ring range based on path steps (approx 26-41)
    INNER_RING_START = 26
    INNER_RING_END = 41
    
    # Count pieces currently in inner ring
    pieces_in_inner = 0
    for pos in player.pieces:
        if pos is not None and INNER_RING_START <= pos <= INNER_RING_END:
            pieces_in_inner += 1
            
    # If moving INTO or WITHIN inner ring and we have <= 1 piece there
    if INNER_RING_START <= new_position <= INNER_RING_END:
        # If we are the only one (or less), restriction applies
        if pieces_in_inner <= 1:
            return True
    return False

def validate_move(game, player, piece_index, dice_value):
    current_pos = player.pieces[piece_index]
    
    # 1. Entry Rules
    if current_pos is None:
        if dice_value in [1, 5, 6]:
            return True, "Enter"
        # Rule 12: Can only move existing pieces, not enter new ones
        return False, "Need 1, 5, or 6 to enter."

    # 2. Calculate New Position
    new_pos = current_pos + dice_value
    
    # 3. Check Victory (Exact Match)
    if new_pos > GameConfig.HOME_INDEX:
        return False, "Move wasted! Need exact number."
        
    # 4. Blood Gate Check
    INNER_GATE_POS = 25
    if current_pos <= INNER_GATE_POS and new_pos > INNER_GATE_POS:
        if not check_blood_gate(player, piece_index):
            return False, "Blood Gate! You need a kill to enter the inner ring."

    # 5. Lone Wolf Restriction
    if check_lone_wolf(player, new_pos):
        if dice_value > 5:
             return False, "Lone Wolf! You need backup to move fast in the inner ring."

    return True, "Valid"
