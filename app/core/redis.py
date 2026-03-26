# backend/app/core/redis.py

class DummyRedis:
    """A temporary in-memory mock of Redis so the app runs without crashing."""
    def __init__(self):
        self.cache = {}

    async def setex(self, name: str, time: int, value: str):
        self.cache[name] = value

    async def get(self, name: str):
        val = self.cache.get(name)
        # Redis always returns bytes, so we mimic that behavior
        return val.encode('utf-8') if val else None

    async def delete(self, name: str):
        if name in self.cache:
            del self.cache[name]
            
    async def publish(self, channel: str, message: str):
        # We will wire this up to real WebSockets later!
        pass 

redis_client = DummyRedis()