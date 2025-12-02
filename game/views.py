# game/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import Game, Player, GameMove, DICE_VALUES
from .serializers import (
    GameSerializer,
    GameCreateSerializer,
    PlayerSerializer,
    PlayerCreateSerializer,
    GameMoveSerializer,
    RollResultSerializer,
    MakeMoveResultSerializer,
)


def broadcast_game_state(room_code, payload=None):
    """
    Helper: broadcast the game's snapshot to all websocket clients in the group.
    If payload is provided, it will be used, otherwise the view will fetch the latest snapshot.
    """
    channel_layer = get_channel_layer()
    group = f"game_{room_code}"
    async_to_sync(channel_layer.group_send)(
        group,
        {
            "type": "game_update",
            "data": payload or {},  # consumer will forward
        },
    )


class GameViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Game. Endpoints:
      - POST /games/            -> create game (GameCreateSerializer)
      - GET  /games/{pk}/       -> game detail (snapshot included)
      - POST /games/{pk}/join/  -> join game (payload: player_name, color, position, optional team)
      - POST /games/{pk}/roll/  -> roll dice (payload: player_id OR position)
      - POST /games/{pk}/move/  -> make move (payload: player_id, piece_index, dice_value)
    """
    queryset = Game.objects.all()
    serializer_class = GameSerializer
    lookup_field = "room_code"  # so endpoints use room_code instead of numeric id

    def get_serializer_class(self):
        if self.action == "create":
            return GameCreateSerializer
        return GameSerializer

    def create(self, request, *args, **kwargs):
        """
        Create a new game.
        Body: { "num_players": 2|4, "team_mode": true|false }
        """
        serializer = GameCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        game = serializer.save()
        # Return the full serialized game
        out = GameSerializer(game).data
        return Response(out, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        """
        Return game snapshot (GameSerializer + extra snapshot fields)
        """
        game = self.get_object()
        return Response(GameSerializer(game).data)

    @action(detail=True, methods=["post"], url_path="join")
    @transaction.atomic
    def join(self, request, room_code=None):
        """
        Join a game.
        Required body: { "player_name": str, "color": "red|blue|green|yellow", "position": int }
        If team_mode True, include "team": 1 or 2.
        """
        game = self.get_object()
        data = request.data.copy()
        # Validate via PlayerCreateSerializer with game context
        serializer = PlayerCreateSerializer(data=data, context={"game": game})
        serializer.is_valid(raise_exception=True)
        player = serializer.create(serializer.validated_data)
        # Attempt auto-start
        game.try_start()
        # Broadcast updated game snapshot
        broadcast_game_state(game.room_code, {"game": game.snapshot()})
        return Response(GameSerializer(game).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="roll")
    @transaction.atomic
    def roll(self, request, room_code=None):
        """
        Roll dice for a player.
        Body: { "player_id": <id> }  OR { "position": <int> }
        Returns: { dice_value, bonus, message, game: <snapshot> }
        """
        game = self.get_object()

        # find player by id or position
        player = None
        player_id = request.data.get("player_id")
        position = request.data.get("position")
        if player_id:
            player = get_object_or_404(Player, pk=player_id, game=game)
        elif position is not None:
            player = get_object_or_404(Player, game=game, position=position)
        else:
            return Response({"detail": "player_id or position required"}, status=400)

        # verify it's player's turn
        if game.current_player != player.position:
            return Response({"detail": "not-player-turn"}, status=400)

        # perform roll (use model helper)
        dice_value = game.roll_for_player(player.position)

        # Return standard roll response (bonus decision will be made after attempting a move/enter)
        roll_payload = {"dice_value": dice_value, "bonus": False, "message": ""}
        # Broadcast roll result to clients (so they can animate dice)
        broadcast_game_state(game.room_code, {"roll": roll_payload, "game": game.snapshot()})

        return Response(RollResultSerializer(roll_payload).data)

    @action(detail=True, methods=["post"], url_path="move")
    @transaction.atomic
    def move(self, request, room_code=None):
        """
        Make a move for a given player's piece.
        Body: {
            "player_id": <id> OR "position": <int>,
            "piece_index": <0..5> OR omit (None) when entering,
            "dice_value": <int>
        }

        Returns MakeMoveResultSerializer
        """
        game = self.get_object()
        player = None
        player_id = request.data.get("player_id")
        position = request.data.get("position")
        if player_id:
            player = get_object_or_404(Player, pk=player_id, game=game)
        elif position is not None:
            player = get_object_or_404(Player, game=game, position=position)
        else:
            return Response({"detail": "player_id or position required"}, status=400)

        dice_value = request.data.get("dice_value")
        if dice_value is None:
            return Response({"detail": "dice_value is required"}, status=400)
        try:
            dice_value = int(dice_value)
        except ValueError:
            return Response({"detail": "dice_value must be integer"}, status=400)
        if dice_value not in DICE_VALUES:
            return Response({"detail": f"invalid dice_value, allowed {DICE_VALUES}"}, status=400)

        piece_index = request.data.get("piece_index")
        if piece_index is not None:
            try:
                piece_index = int(piece_index)
            except ValueError:
                return Response({"detail": "piece_index must be integer 0..5"}, status=400)

        # Ensure it's player's turn
        if game.current_player != player.position:
            return Response({"detail": "not-player-turn"}, status=400)

        # Use Player.make_move (synchronous, returns result dict)
        result = player.make_move(piece_index if piece_index is not None else (player.first_offboard_index() if player.can_enter_with_roll(dice_value) else None), dice_value)

        # If not ok, return reason
        if not result.get("ok"):
            return Response(MakeMoveResultSerializer({
                "ok": False,
                "reason": result.get("reason"),
                "from_position": result.get("from"),
                "to_position": result.get("to"),
                "captured": result.get("captured"),
                "bonus": False,
                "game": GameSerializer(game).data,
            }).data, status=400)

        # Log the move to GameMove
        gm = GameMove.objects.create(
            game=game,
            player=player,
            dice_value=dice_value,
            piece_index=piece_index,
            from_position=str(result.get("from")),
            to_position=str(result.get("to")),
            captured_player_pos=(result.get("captured") or {}).get("player_position"),
            captured_piece_idx=(result.get("captured") or {}).get("piece_index"),
            bonus_awarded=bool(result.get("bonus")),
        )

        # Advance turn if no bonus; if bonus is True, current_player remains same
        game.advance_turn(bonus=bool(result.get("bonus")))

        # Broadcast updated game snapshot and the move
        broadcast_game_state(game.room_code, {"move": GameMoveSerializer(gm).data, "game": game.snapshot()})

        # Prepare response
        response_payload = {
            "ok": True,
            "reason": None,
            "from_position": result.get("from"),
            "to_position": result.get("to"),
            "captured": result.get("captured"),
            "bonus": bool(result.get("bonus")),
            "game": GameSerializer(game).data,
        }
        return Response(MakeMoveResultSerializer(response_payload).data)
