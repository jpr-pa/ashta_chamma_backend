# game/serializers.py
from rest_framework import serializers
from .models import Game, Player, GameMove

class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'player_name', 'color', 'position', 'pieces', 'kills', 'finished', 'team']

class GameSerializer(serializers.ModelSerializer):
    players = PlayerSerializer(many=True, read_only=True)
    
    class Meta:
        model = Game
        fields = ['id', 'room_code', 'num_players', 'team_mode', 'status', 
                  'current_player', 'winner', 'players', 'created_at']

class GameMoveSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameMove
        fields = ['id', 'player', 'dice_value', 'piece_index', 'from_position', 
                  'to_position', 'captured', 'timestamp']

class CreateGameSerializer(serializers.Serializer):
    num_players = serializers.ChoiceField(choices=[2, 4])
    team_mode = serializers.BooleanField(default=False)
    player_name = serializers.CharField(max_length=50)
    colors = serializers.ListField(child=serializers.CharField())

class JoinGameSerializer(serializers.Serializer):
    room_code = serializers.CharField(max_length=6)
    player_name = serializers.CharField(max_length=50)
    color = serializers.CharField()

class MakeMoveSerializer(serializers.Serializer):
    room_code = serializers.CharField(max_length=6)
    player_position = serializers.IntegerField()
    dice_value = serializers.IntegerField()
    piece_index = serializers.IntegerField()
