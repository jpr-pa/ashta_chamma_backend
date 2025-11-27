# game/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Game, Player, GameMove
from .serializers import *
from .game_logic import validate_move, GameConfig
import random
import string

class GameViewSet(viewsets.ModelViewSet):
    queryset = Game.objects.all()
    serializer_class = GameSerializer
    
    def generate_room_code(self):
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Game.objects.filter(room_code=code).exists():
                return code
    
    @action(detail=False, methods=['post'])
    def create_game(self, request):
        serializer = CreateGameSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            game = Game.objects.create(
                room_code=self.generate_room_code(),
                num_players=data['num_players'],
                team_mode=data['team_mode'],
                status='waiting'
            )
            for idx, color in enumerate(data['colors']):
                Player.objects.create(
                    game=game,
                    player_name=f"{data['player_name']} {idx+1}" if idx > 0 else data['player_name'],
                    color=color,
                    position=idx,
                    pieces=[None] * 6,
                    kills=[0] * 6,
                    team=(idx // 2 + 1) if data['team_mode'] else None
                )
            return Response(GameSerializer(game).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def join_game(self, request):
        serializer = JoinGameSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            game = get_object_or_404(Game, room_code=data['room_code'])
            
            if game.status != 'waiting':
                return Response({'error': 'Game already started'}, status=status.HTTP_400_BAD_REQUEST)
            if game.players.count() >= game.num_players:
                return Response({'error': 'Game is full'}, status=status.HTTP_400_BAD_REQUEST)
            
            position = game.players.count()
            Player.objects.create(
                game=game,
                player_name=data['player_name'],
                color=data['color'],
                position=position,
                pieces=[None] * 6,
                kills=[0] * 6,
                team=(position // 2 + 1) if game.team_mode else None
            )
            
            if game.players.count() == game.num_players:
                game.status = 'in_progress'
                game.save()
            
            return Response(GameSerializer(game).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def get_game(self, request):
        room_code = request.query_params.get('room_code')
        game = get_object_or_404(Game, room_code=room_code)
        return Response(GameSerializer(game).data)

    @action(detail=False, methods=['post'])
    def roll_dice(self, request):
        room_code = request.data.get('room_code')
        game = get_object_or_404(Game, room_code=room_code)
        
        # Ashta Chamma Dice Probabilities (Optional enhancement)
        choices = [1, 2, 3, 4, 5, 6, 12]
        dice_value = random.choice(choices)
        
        return Response({'dice_value': dice_value}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def make_move(self, request):
        serializer = MakeMoveSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            game = get_object_or_404(Game, room_code=data['room_code'])
            player = game.players.get(position=data['player_position'])
            dice_val = data['dice_value']
            piece_idx = data['piece_index']
            
            # 1. Validate Move Logic
            is_valid, msg = validate_move(game, player, piece_idx, dice_val)
            if not is_valid:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Execute Move
            pieces = player.pieces.copy()
            from_pos = pieces[piece_idx]
            
            if from_pos is None:
                # Entry logic
                if dice_val == 1: to_pos = 0
                elif dice_val == 5: to_pos = 0 # Usually enters 1 piece
                elif dice_val == 6: to_pos = 0
                else: to_pos = 0 # Fallback
            else:
                # Normal movement
                # Handle Lone Wolf Cap
                # if is_lone_wolf and dice_val > 5: move only 5
                to_pos = from_pos + dice_val

            pieces[piece_idx] = to_pos
            player.pieces = pieces
            
            # 3. Capture Logic (Simplified for MVP)
            # We need to translate 'to_pos' (linear) to actual Grid ID to check collisions
            # This requires the Path Map to be shared or calculated here.
            # For now, we assume no capture if we don't map coordinates in backend.
            # Ideally: Convert `to_pos` -> `(x,y)`. Check other players at `(x,y)`.
            captured = False
            # if not is_safe_zone(to_pos) and enemy_at(to_pos):
            #    enemy.piece = None (send home)
            #    player.kills[piece_idx] += 1
            #    captured = True

            # 4. Check Victory
            if to_pos == 53: # Home index
                player.finished += 1
                if player.finished == 6:
                    game.winner = player.position
                    game.status = 'completed'

            player.save()
            
            # 5. Next Turn Logic
            # Bonus turn if 1, 5, 6, 12 OR Captured
            bonus_values = [1, 5, 6, 12]
            if dice_val not in bonus_values and not captured:
                game.current_player = (game.current_player + 1) % game.num_players
            
            game.save()
            
            return Response(GameSerializer(game).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
