# game/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.crypto import get_random_string
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Game
from .serializers import GameSerializer


class GameViewSet(viewsets.ModelViewSet):
    """
    API endpoints for:
      POST /api/games/              -> create a new game
      GET  /api/games/<room_code>/  -> fetch game
      POST /api/games/join/         -> join existing game
      POST /api/games/<room_code>/roll/ -> roll dice
      POST /api/games/<room_code>/move/ -> make move
    """

    queryset = Game.objects.all()
    serializer_class = GameSerializer
    lookup_field = "room_code"

    # ------------------------------------------------------
    # CREATE GAME
    # ------------------------------------------------------
    def create(self, request, *args, **kwargs):
        """
        Creates a new game.
        Expected payload:
        {
            "num_players": 4,
            "team_mode": false,
            "player_name": "Alice",
            "colors": ["red","blue","green","yellow"]
        }
        """
        room_code = get_random_string(6).upper()

        game = Game.objects.create(
            room_code=room_code,
            num_players=request.data.get("num_players"),
            team_mode=request.data.get("team_mode", False),
        )

        # Add creator as first player
        game.add_player(
            player_name=request.data.get("player_name"),
            color=request.data.get("colors")[0]
        )

        serializer = GameSerializer(game)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------
    # JOIN GAME
    # ------------------------------------------------------
    @action(detail=False, methods=["post"])
    def join(self, request):
        """
        Expected payload:
        {
            "room_code": "ABC123",
            "player_name": "Bob",
            "color": "blue"
        }
        """
        room_code = request.data.get("room_code")
        game = get_object_or_404(Game, room_code=room_code)

        if game.status != "waiting":
            return Response({"detail": "Game already started"}, status=400)

        try:
            game.add_player(
                player_name=request.data.get("player_name"),
                color=request.data.get("color")
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=400)

        game.save()
        self.broadcast_update(game)

        return Response(GameSerializer(game).data)

    # ------------------------------------------------------
    # ROLL DICE
    # ------------------------------------------------------
    @action(detail=True, methods=["post"])
    def roll(self, request, room_code=None):
        """
        Expected payload:
        {
            "player_position": 0
        }
        """
        game = get_object_or_404(Game, room_code=room_code)
        player_pos = request.data.get("player_position")

        try:
            result = game.roll_for_player(player_pos)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)

        game.save()
        self.broadcast_update(game)

        return Response(result)

    # ------------------------------------------------------
    # MAKE MOVE
    # ------------------------------------------------------
    @action(detail=True, methods=["post"])
    def move(self, request, room_code=None):
        """
        Expected payload:
        {
            "player_position": 0,
            "piece_index": 1,
            "dice_value": 6
        }
        """
        game = get_object_or_404(Game, room_code=room_code)

        try:
            result = game.make_move(request.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)

        game.save()
        self.broadcast_update(game)

        return Response(result)

    # ------------------------------------------------------
    # WEBSOCKET BROADCAST
    # ------------------------------------------------------
    def broadcast_update(self, game):
        """Push updated game state to all WebSocket clients"""

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"game_{game.room_code}",
            {
                "type": "game_update",
                "game_data": GameSerializer(game).data,
            }
        )
