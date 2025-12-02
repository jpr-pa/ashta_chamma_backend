# game/serializers.py
from rest_framework import serializers
from .models import Game, Player, GameMove, SAFE_ZONES, HOME_INDEX, ENTRY_BY_COLOR


class PlayerSerializer(serializers.ModelSerializer):
    """
    Read-only / general-purpose serializer for Player instances.
    """
    class Meta:
        model = Player
        fields = [
            "id",
            "player_name",
            "color",
            "position",
            "pieces",
            "kills",
            "finished",
            "team",
        ]
        read_only_fields = ["id", "kills", "finished"]


class PlayerCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used when a player is joining/created.
    Ensures color uniqueness within the same game and initializes pieces.
    """
    class Meta:
        model = Player
        fields = ["id", "player_name", "color", "position", "team"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        game = self.context.get("game")
        if game is None:
            raise serializers.ValidationError("Game context is required to create a player.")

        color = attrs.get("color")
        # Make sure the color isn't already taken in this game
        if game.players.filter(color=color).exists():
            raise serializers.ValidationError({"color": "This color is already taken in this game."})

        # Validate position uniqueness
        position = attrs.get("position")
        if position is None:
            raise serializers.ValidationError({"position": "Position (turn order) is required."})
        if game.players.filter(position=position).exists():
            raise serializers.ValidationError({"position": "This position is already taken in the game."})

        # If team mode, ensure team assignment is either 1 or 2
        if game.team_mode:
            team = attrs.get("team")
            if team not in (1, 2):
                raise serializers.ValidationError({"team": "Team must be 1 or 2 in team_mode."})

        return attrs

    def create(self, validated_data):
        """
        Initialize pieces list to six None entries and default kills/finished to 0.
        """
        game = self.context.get("game")
        if game is None:
            raise serializers.ValidationError("Game context required.")

        # Initialize pieces to exactly six None entries
        validated_data.setdefault("pieces", [None] * 6)
        validated_data.setdefault("kills", 0)
        validated_data.setdefault("finished", 0)

        player = Player.objects.create(game=game, **validated_data)
        # After creating player, attempt to auto-start the game if full
        game.try_start()
        return player


class GameMoveSerializer(serializers.ModelSerializer):
    """
    Serializer for logging/reading moves.
    """
    player_name = serializers.CharField(source="player.player_name", read_only=True)
    player_position = serializers.IntegerField(source="player.position", read_only=True)

    class Meta:
        model = GameMove
        fields = [
            "id",
            "game",
            "player",
            "player_name",
            "player_position",
            "dice_value",
            "piece_index",
            "from_position",
            "to_position",
            "captured_player_pos",
            "captured_piece_idx",
            "bonus_awarded",
            "timestamp",
        ]
        read_only_fields = ["id", "timestamp", "player_name", "player_position"]


class GameSerializer(serializers.ModelSerializer):
    """
    Serializer for reading Game instances with nested players.
    """
    players = PlayerSerializer(many=True, read_only=True)
    # Provide a small computed summary (optional)
    player_count = serializers.SerializerMethodField()
    safe_zones = serializers.ListField(child=serializers.IntegerField(), read_only=True)
    home_index = serializers.IntegerField(read_only=True, default=HOME_INDEX)

    class Meta:
        model = Game
        fields = [
            "id",
            "room_code",
            "num_players",
            "team_mode",
            "status",
            "current_player",
            "winner",
            "players",
            "player_count",
            "safe_zones",
            "home_index",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "room_code", "status", "players", "created_at", "updated_at", "safe_zones", "home_index"]

    def get_player_count(self, obj):
        return obj.players.count()

    def to_representation(self, instance):
        """
        Extend representation with 'snapshot' style data for frontend convenience.
        This duplicates some data but makes frontend integration simpler.
        """
        rep = super().to_representation(instance)
        # Add a compact players list matching the snapshot format in models.py
        rep["snapshot_players"] = [
            {
                "player_name": p.player_name,
                "color": p.color,
                "position": p.position,
                "pieces": p.pieces,
                "kills": p.kills,
                "finished": p.finished,
                "team": p.team,
            } for p in instance.players.order_by("position")
        ]
        # add safe_zones and home_index
        rep["safe_zones"] = sorted(list(SAFE_ZONES))
        rep["home_index"] = HOME_INDEX
        return rep


class GameCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used to create a new Game.
    Room code will be generated by model default if not provided.
    """
    class Meta:
        model = Game
        fields = ["id", "room_code", "num_players", "team_mode"]
        read_only_fields = ["id", "room_code"]

    def create(self, validated_data):
        # create and return game
        game = Game.objects.create(**validated_data)
        return game


# Small helper serializers / actions for game operations (optional convenience)

class RollResultSerializer(serializers.Serializer):
    """
    Serializer for returning a dice roll result to the frontend.
    """
    dice_value = serializers.IntegerField()
    bonus = serializers.BooleanField()
    message = serializers.CharField(allow_blank=True)


class MakeMoveResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True, allow_blank=True)
    from_position = serializers.CharField(allow_null=True)
    to_position = serializers.CharField(allow_null=True)
    captured = serializers.DictField(child=serializers.IntegerField(), allow_null=True, required=False)
    bonus = serializers.BooleanField()
    game = GameSerializer(read_only=True)
