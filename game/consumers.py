# game/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class GameConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for a single game room.
    Clients should connect to: ws://.../ws/game/<room_code>/
    The REST views broadcast messages to the group name "game_<room_code>" with:
      { "type": "game_update", "data": {...} }

    This consumer simply forwards that "data" payload to every connected client.
    """

    async def connect(self):
        self.room_code = self.scope["url_route"]["kwargs"]["room_code"]
        self.group_name = f"game_{self.room_code}"

        # Join group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Optionally: send a welcome or request initial state (frontend usually fetches via REST)
        await self.send_json({
            "type": "connected",
            "room_code": self.room_code,
            "message": "connected to game websocket",
        })

    async def disconnect(self, close_code):
        # Leave group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Optionally handle messages from clients (like chat or manual actions).
        For now we ignore client->server messages (we rely on REST endpoints).
        """
        # You could optionally accept client pings or commands here.
        pass

    async def game_update(self, event):
        """
        Handler for messages sent to the group by server-side code.
        The event's "data" property should be JSON-serializable.
        We'll forward it directly to the websocket client.
        """
        data = event.get("data", {})
        # Ensure always send type field
        payload = {
            "type": "game_update",
            "data": data,
        }
        await self.send(text_data=json.dumps(payload))
