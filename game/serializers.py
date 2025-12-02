# game/serializers.py
from rest_framework import serializers
from .models import Game


class PlayerSerializer(serializers.Serializer):
    """
    Represents a single player inside Game.players array
    """
    player_name = serializers.CharField()
    color = serializers.CharField()
    pieces = serializers.ListField(child=serializers.IntegerField(allow_null=True))
    finished = serializers.IntegerField()
    position = serializers.IntegerField()  # 0,1,2,3 – used by frontend


class GameSerializer(serializers.ModelSerializer):
    """
    Full game state serializer sent to frontend.
    Turns the Python list/dict structures in Game.players and Game.board
    into JSON-friendly data.
    """
    players = serializers.SerializerMethodField()
    board = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "room_code",
            "num_players",
            "team_mode",
            "status",
            "current_player",
            "winner",
            "players",
            "board",
        ]

    # -------------------------------------
    # PLAYERS → frontend format
    # -------------------------------------
    def get_players(self, obj):
