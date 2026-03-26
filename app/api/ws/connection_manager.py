import json
import asyncio
from typing import Dict
from fastapi import WebSocket
from app.core.redis import redis_client

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pubsub = redis_client.pubsub()
        self._listener_started = False  # Track if listener is already running

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        
        # Start the background task ONLY ONCE per server instance
        if not self._listener_started:
            await self.pubsub.subscribe("dunex_global_stream")
            asyncio.create_task(self._listen_to_redis())
            self._listener_started = True

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def broadcast_to_channel(self, message: dict):
        payload = json.dumps(message)
        await redis_client.publish("dunex_global_stream", payload)

    async def _listen_to_redis(self):
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8") # Ensure it's decoded to string
                    
                    # Convert dictionary keys to a list to avoid "dictionary changed size during iteration" errors
                    for user_id in list(self.active_connections.keys()):
                        connection = self.active_connections.get(user_id)
                        if connection:
                            try:
                                await connection.send_text(data)
                            except Exception:
                                self.disconnect(user_id)
        except Exception as e:
            print(f"Redis listener encountered an error: {e}")
            self._listener_started = False

manager = ConnectionManager()