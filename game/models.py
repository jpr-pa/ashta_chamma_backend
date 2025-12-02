# game/models.py
from django.db import models
from django.utils.crypto import get_random_string
import random

# ---------------------------
# Board definition (exact)
# ---------------------------
# This mapping matches the exact 7x7 table you provided.
# Format: GRID[row][col] = index (0..48), 'S' suffix was used earlier to mark safe zones and 'H' for home.
# We'll create index->(row,col) and safe zones using the provided table.

GRID = [
    [21, 20, 19, 18, 17, 16, 15],
    [22, 24, 25, 26, 27, 28, 14],
    [23, 39, 40, 41, 42, 29, 13],
    [0,  38, 47, 48, 43, 30, 12],
    [1,  37, 46, 45, 44, 31, 11],
    [2,  36, 35, 34, 33, 32, 10],
    [3,   4,  5,  6,  7,  8,  9],
]

# Safe zones as per your table (indexes with S)
SAFE_ZONES = {18, 24, 28, 41, 0, 47, 43, 12, 45, 36, 32, 6}

# Home index:
HOME_INDEX = 48

# Build index -> (r,c) and r,c -> index
INDEX_TO_COORD = {}
COORD_TO_INDEX = {}
for r in range(7):
    for c in range(7):
        idx = GRID[r][c]
        INDEX_TO_COORD[idx] = (r, c)
        COORD_TO_INDEX[(r, c)] = idx

# Useful helper to detect rings by Manhattan max distance from center (3,3)
def ring_for_index(idx):
    r, c = INDEX_TO_COORD[idx]
    d = max(abs(r - 3), abs(c - 3))
    # d == 3 => outer ring, d == 2 => inner ring (5x5 perimeter),
    # d == 1 => middle ring (3x3 perimeter), d == 0 => home
    return d  # 3,2,1,0

# Entry positions for players (choose four evenly spaced outer-entry indices)
# These are chosen to be quarters: 0,12,24,36 from your table (they are well distributed)
ENTRY_BY_COLOR = {
    'red': 0,
    'blue': 12,
    'green': 24,
    'yellow': 36,
}

# Dice values set (allowed values)
DICE_VALUES = [1, 2, 3, 4, 5, 6, 12]
ENTRY_VALUES = {1, 5, 6}  # can enter with these
BONUS_VALUES = {1, 5, 6, 12}

# Random room code
def random_room_code():
    return get_random_string(6).upper()

# ---------------------------
# Models
# ---------------------------

class Game(models.Model):
    GAME_STATUS = [
        ('waiting', 'Waiting'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    room_code = models.CharField(max_length=6, unique=True, default=random_room_code)
    num_players = models.IntegerField(choices=[(2, '2 Players'), (4, '4 Players')])
    team_mode = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=GAME_STATUS, default='waiting')
    current_player = models.IntegerField(default=0)  # position index: 0..num_players-1
    winner = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # convenience: return serialized minimal state for frontend (you can expand in serializer)
    def snapshot(self):
        players = []
        for p in self.players.order_by('position'):
            players.append({
                "player_name": p.player_name,
                "color": p.color,
                "position": p.position,
                "pieces": p.pieces,
                "kills": p.kills,
                "finished": p.finished,
                "team": p.team,
            })

        return {
            "room_code": self.room_code,
            "num_players": self.num_players,
            "team_mode": self.team_mode,
            "status": self.status,
            "current_player": self.current_player,
            "winner": self.winner,
            "players": players,
        }

    def try_start(self):
        if self.status == 'waiting' and self.players.count() == self.num_players:
            self.status = 'in_progress'
            self.save()

    def roll_for_player(self, player_position):
        # Basic guard:
        if self.status != 'in_progress':
            raise ValueError("Game not in progress")
        if player_position != self.current_player:
            raise ValueError("Not player's turn")

        return random.choice(DICE_VALUES)

    def advance_turn(self, bonus=False):
        if not bonus:
            self.current_player = (self.current_player + 1) % self.num_players
            self.save()

    def check_and_set_winner(self, player):
        # For solo mode: first to 6 finished
        if not self.team_mode:
            if player.finished >= 6:
                self.status = 'completed'
                self.winner = player.position
                self.save()
                return True
            return False
        # For team mode: team wins when both members combined reach 12
        else:
            team = player.team
            teammates = self.players.filter(team=team)
            total = sum(t.finished for t in teammates)
            if total >= 12:
                # set winner as the team (we'll store winner as the position of this player for simplicity)
                self.status = 'completed'
                self.winner = player.position
                self.save()
                return True
            return False

    def __str__(self):
        return f"Game {self.room_code} ({self.status})"


class Player(models.Model):
    COLORS = [
        ('red', 'Red'),
        ('blue', 'Blue'),
        ('green', 'Green'),
        ('yellow', 'Yellow'),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='players')
    player_name = models.CharField(max_length=50)
    color = models.CharField(max_length=10, choices=COLORS)
    position = models.IntegerField()  # turn order 0..num_players-1

    # pieces -> list of 6 entries: None (off-board), 0..48 (path index), or 'HOME'
    pieces = models.JSONField(default=list)  # should be length 6
    # number of kills performed by this player (for blood gate)
    kills = models.IntegerField(default=0)
    finished = models.IntegerField(default=0)
    team = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('game', 'position')

    def save(self, *args, **kwargs):
        # ensure pieces array length 6
        if not isinstance(self.pieces, list) or len(self.pieces) != 6:
            # initialize as all off-board
            self.pieces = [None] * 6
        super().save(*args, **kwargs)

    def pieces_on_board(self):
        return [p for p in self.pieces if (p is not None and p != "HOME")]

    def count_in_inner_or_middle(self):
        # inner ring (d==2) and middle ring (d==1)
        cnt = 0
        for p in self.pieces:
            if p is None or p == "HOME":
                continue
            d = ring_for_index(p)
            if d in (1, 2):
                cnt += 1
        return cnt

    def can_enter_with_roll(self, roll):
        # must have at least one empty piece slot to enter
        if all((x == "HOME" or x is not None) for x in self.pieces):
            return False
        if roll in ENTRY_VALUES:
            return True
        if roll == 12:
            # 12 can be used only if player has at least one piece already on board
            return any(x is not None and x != "HOME" for x in self.pieces)
        return False

    def first_offboard_index(self):
        for i in range(6):
            if self.pieces[i] is None:
                return i
        return None

    def entry_index(self):
        # returns the entry path index for this player's color
        return ENTRY_BY_COLOR[self.color]

    # attempt to enter a piece (when roll allows entry)
    def enter_piece(self, roll):
        if not self.can_enter_with_roll(roll):
            raise ValueError("Cannot enter with this roll")

        piece_idx = self.first_offboard_index()
        if piece_idx is None:
            raise ValueError("No off-board pieces")

        start_pos = self.entry_index()

        # If the entry square is occupied by another friendly piece, that's fine (stacking allowed).
        # If occupied by enemy non-safe square -> capture occurs (handled outside).
        self.pieces[piece_idx] = start_pos
        self.save()
        return piece_idx, start_pos

    # main move function: attempts to move a piece specified by piece_index by 'roll'
    # returns dict: {ok: bool, reason: str or None, from: idx, to: idx, captured: {player_pos, piece_index} or None, bonus: bool}
    def make_move(self, piece_index, roll):
        if self.game.status != 'in_progress':
            return {"ok": False, "reason": "game-not-active"}

        # validate piece index
        if not (0 <= piece_index < 6):
            return {"ok": False, "reason": "invalid-piece-index"}

        cur = self.pieces[piece_index]

        # If piece off-board, only enter rules apply
        if cur is None:
            if not self.can_enter_with_roll(roll):
                return {"ok": False, "reason": "cannot-enter-with-this-roll"}
            # entering
            entry_idx = self.entry_index()

            # Check blood gate: entering inner ring isn't possible until player has at least 1 kill
            # But entering typically puts you on outer ring (entry indices chosen are outer). So this generally is fine.
            # Place piece
            self.pieces[piece_index] = entry_idx
            self.save()

            # Resolve capture (if landing on non-safe enemy)
            captured_info = self._resolve_capture_on_index(entry_idx)
            bonus = (roll in BONUS_VALUES) or (captured_info is not None)
            # record move outside by caller (views/consumers)
            return {"ok": True, "from": None, "to": entry_idx, "captured": captured_info, "bonus": bonus}

        # If piece already HOME
        if cur == "HOME":
            return {"ok": False, "reason": "piece-already-home"}

        # Moving an on-board piece:
        origin_idx = cur
        origin_ring = ring_for_index(origin_idx)
        # Lone wolf restriction:
        # Count player's warriors inside inner ring (d <=2 and not HOME)
        inner_middle_count = self.count_in_inner_or_middle()
        # If exactly 1 inside inner ring OR middle ring (i.e., inner_middle_count == 1), that lone warrior limited to 5 steps per turn
        effective_roll = roll
        if inner_middle_count == 1:
            # if this piece is the only one inside the inner/middle rings, limit its movement to 5
            # But only applies if this piece is in inner/middle rings
            if ring_for_index(origin_idx) in (1, 2):
                if roll > 5:
                    effective_roll = 5

        # Compute destination index (linear path increase)
        dest = origin_idx + effective_roll

        # If destination beyond HOME_INDEX, it's invalid/wasted (must land exactly)
        if dest > HOME_INDEX:
            return {"ok": False, "reason": "overshoot-home"}

        # If destination is HOME_INDEX, we move to HOME only if exact
        captured_info = None

        # If moving from outer to inner (origin_ring==3 and dest_ring <=2) enforce Blood Gate
        dest_ring = ring_for_index(dest) if dest != HOME_INDEX else 0
        if origin_ring == 3 and dest_ring <= 2:
            if self.kills == 0:
                # Blood Gate blocks the move
                return {"ok": False, "reason": "blood-gate-blocked"}

        # If destination is a safe zone, capturing not allowed
        # But if destination is occupied by enemy on non-safe zone -> capture
        # Note: if multiple enemies present (allowed on safe zones) we consider stacking multiple pieces; capturing rules should only remove single piece if landed on non-safe single occupant.

        # Check for exact home
        if dest == HOME_INDEX:
            # Move piece to HOME
            self.pieces[piece_index] = "HOME"
            self.finished += 1
            self.save()
            # No capture at home
            # bonus if roll in BONUS_VALUES (1,5,6,12) OR capturing (none)
            bonus = (roll in BONUS_VALUES)
            # check for victory
            self.game.check_and_set_winner(self)
            return {"ok": True, "from": origin_idx, "to": "HOME", "captured": None, "bonus": bonus}

        # Normal movement to dest (not home)
        # Check if someone occupies dest; multiple pieces from same player can share a square (allowed),
        # but if an opponent occupies dest on a non-safe square, capture occurs.
        # We need to find any opponent pieces on dest (since pieces are stored per player).
        if dest not in SAFE_ZONES:
            # iterate opponents to find any occupying piece at 'dest'
            for opponent in self.game.players.exclude(id=self.id):
                for opp_idx, opp_pos in enumerate(opponent.pieces):
                    if opp_pos == dest:
                        # Underdog protection:
                        # If opponent has >=2 warriors in inner/middle rings and this player has exactly 1 there,
                        # then this player's lone warrior is immune to capture by that opponent.
                        opp_inner = opponent.count_in_inner_or_middle()
                        my_inner = self.count_in_inner_or_middle()
                        # If opp_inner >=2 and my_inner == 1 and dest is our lone piece, protect (no capture)
                        if opp_inner >= 2 and my_inner == 1:
                            # no capture happens
                            captured_info = None
                        else:
                            # capture opponent piece: set their piece back to None (off-board) and increment kills
                            opponent.pieces[opp_idx] = None
                            opponent.save()
                            self.kills += 1
                            self.save()
                            captured_info = {"player_position": opponent.position, "piece_index": opp_idx}
                        # only one piece is captured per landing
                        break
                if captured_info:
                    break

        # Move piece
        self.pieces[piece_index] = dest
        self.save()

        # Bonus rules: roll in BONUS_VALUES or capture
        bonus = (roll in BONUS_VALUES) or (captured_info is not None)

        return {"ok": True, "from": origin_idx, "to": dest, "captured": captured_info, "bonus": bonus}

    def _resolve_capture_on_index(self, idx):
        """
        Helper: when a piece lands on idx (e.g., on entry), check if enemies there to capture (if non-safe),
        perform capture and return captured info or None.
        """
        if idx in SAFE_ZONES:
            return None
        for opponent in self.game.players.exclude(id=self.id):
            for opp_idx, opp_pos in enumerate(opponent.pieces):
                if opp_pos == idx:
                    # check underdog protection
                    opp_inner = opponent.count_in_inner_or_middle()
                    my_inner = self.count_in_inner_or_middle()
                    if opp_inner >= 2 and my_inner == 1:
                        return None
                    opponent.pieces[opp_idx] = None
                    opponent.save()
                    self.kills += 1
                    self.save()
                    return {"player_position": opponent.position, "piece_index": opp_idx}
        return None

    def __str__(self):
        return f"{self.player_name} ({self.color})"

# ---------------------------
# Move logging
# ---------------------------
class GameMove(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='moves')
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    dice_value = models.IntegerField()
    piece_index = models.IntegerField(null=True, blank=True)  # piece slot moved (0..5) or null if entry was automatic
    from_position = models.CharField(max_length=16, null=True, blank=True)  # 'None' or 'HOME' or index
    to_position = models.CharField(max_length=16)  # index or 'HOME'
    captured_player_pos = models.IntegerField(null=True, blank=True)
    captured_piece_idx = models.IntegerField(null=True, blank=True)
    bonus_awarded = models.BooleanField(default=False)

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Move {self.id} game={self.game.room_code} by={self.player.player_name}"
