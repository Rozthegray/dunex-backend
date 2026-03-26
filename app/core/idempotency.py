from typing import Callable
from fastapi import Request, Response
from fastapi.routing import APIRoute

class IdempotentRoute(APIRoute):
    """
    Custom APIRoute class that intercepts requests to prevent duplicate transactions.
    It looks for the Idempotency-Key header on POST/PUT/PATCH requests.
    """
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            # 1. We only care about requests that modify data
            if request.method in ["POST", "PUT", "PATCH"]:
                idempotency_key = request.headers.get("Idempotency-Key")
                
                # Note: In production, you would check redis_client.get(f"idemp_{idempotency_key}") here
                # to instantly return a cached response if the user double-tapped the submit button.
            
            # 2. Execute the actual endpoint logic
            response: Response = await original_route_handler(request)
            
            # Note: In production, you would save the response to Redis here using the idempotency_key
            
            return response

        return custom_route_handler