from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from app.core.redis import redis_client

router = APIRouter(tags=["Real-time Notifications"])

@router.websocket("/ws/notifications/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    
    # Subscribe to the user's private channel AND the global broadcast channel
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"user_notifications_{user_id}", "dunex_global_stream")
    
    try:
        while True:
            # Check for new messages from Redis every 0.1 seconds
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                data = message["data"].decode("utf-8")
                
                # If it's a raw string, wrap it in JSON. If it's already JSON, send it.
                try:
                    json_data = json.loads(data)
                    await websocket.send_json(json_data)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "direct_message", "message": data})
            
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        print(f"User {user_id} disconnected from WebSocket.")
    finally:
        await pubsub.unsubscribe(f"user_notifications_{user_id}", "dunex_global_stream")