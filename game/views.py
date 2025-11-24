# game/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Game, Player, GameMove
from .serializers import *
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
            
            # Create game
            game = Game.objects.create(
                room_code=self.generate_room_code(),
                num_players=data['num_players'],
                team_mode=data['team_mode'],
                status='waiting'
            )
            
            # Create players
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
            
            # Start game if all players joined
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
        
        dice_values = [1, 2, 3, 4, 5, 6, 12]
        dice_value = random.choice(dice_values)
        
        return Response({'dice_value': dice_value}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def make_move(self, request):
        serializer = MakeMoveSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            game = get_object_or_404(Game, room_code=data['room_code'])
            player = game.players.get(position=data['player_position'])
            
            # Update player pieces
            pieces = player.pieces.copy()
            piece_idx = data['piece_index']
            from_pos = pieces[piece_idx]
            
            if from_pos is None:
                to_pos = 0
            else:
                to_pos = from_pos + data['dice_value']
            
            pieces[piece_idx] = to_pos
            player.pieces = pieces
            
            # Check if reached home
            if to_pos >= 50:
                player.finished += 1
                if player.finished == 6:
                    game.winner = player.position
                    game.status = 'completed'
            
            player.save()
            
            # Record move
            GameMove.objects.create(
                game=game,
                player=player,
                dice_value=data['dice_value'],
                piece_index=piece_idx,
                from_position=from_pos,
                to_position=to_pos
            )
            
            # Move to next player if no bonus
            bonus_values = [1, 5, 6, 12]
            if data['dice_value'] not in bonus_values:
                game.current_player = (game.current_player + 1) % game.num_players
            
            game.save()
            
            return Response(GameSerializer(game).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
