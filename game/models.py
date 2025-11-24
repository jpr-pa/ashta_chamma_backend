# game/models.py
from django.db import models
from django.contrib.auth.models import User
import json

class Game(models.Model):
    GAME_STATUS = [
        ('waiting', 'Waiting'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    room_code = models.CharField(max_length=6, unique=True)
    num_players = models.IntegerField(choices=[(2, '2 Players'), (4, '4 Players')])
    team_mode = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=GAME_STATUS, default='waiting')
    current_player = models.IntegerField(default=0)
    winner = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Game {self.room_code} - {self.status}"

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
    position = models.IntegerField()  # 0, 1, 2, 3
    pieces = models.JSONField(default=list)  # [null, null, null, null, null, null]
    kills = models.JSONField(default=list)  # [0, 0, 0, 0, 0, 0]
    finished = models.IntegerField(default=0)
    team = models.IntegerField(null=True, blank=True)  # 1 or 2 for team mode
    
    class Meta:
        unique_together = ['game', 'position']
    
    def __str__(self):
        return f"{self.player_name} ({self.color}) in {self.game.room_code}"

class GameMove(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='moves')
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    dice_value = models.IntegerField()
    piece_index = models.IntegerField()
    from_position = models.IntegerField(null=True)
    to_position = models.IntegerField()
    captured = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Move in {self.game.room_code} by {self.player.player_name}"
