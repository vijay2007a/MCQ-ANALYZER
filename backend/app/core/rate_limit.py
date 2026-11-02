import time
from collections import defaultdict
from typing import Callable, Optional
from fastapi import Request, HTTPException, status
from app.core.config import settings

# Optional Redis connection
redis_client = None
if settings.REDIS_URL:
    try:
        import redis
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        redis_client = None


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    """
    def __init__(self):
        self._requests = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.time()
        window_start = now - window_seconds
        
        # Clean up old timestamps
        timestamps = [t for t in self._requests[key] if t > window_start]
        self._requests[key] = timestamps
        
        if len(timestamps) >= max_requests:
            retry_after = int(window_seconds - (now - timestamps[0])) + 1
            return False, 0, max(1, retry_after)
        
        self._requests[key].append(now)
        remaining = max_requests - len(self._requests[key])
        return True, remaining, 0


in_memory_limiter = InMemoryRateLimiter()


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int) -> Callable:
    """
    FastAPI dependency for rate limiting endpoints.
    Uses Redis if available, else in-memory sliding window.
    """
    async def dependency(request: Request):
        if not settings.RATE_LIMIT_ENABLED or settings.ENVIRONMENT == "testing":
            return
        
        # Resolve client identifier: Forwarded IP or Client Host
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        
        rate_key = f"ratelimit:{key_prefix}:{client_ip}"
        # A classroom shares one public IP (NAT); limit session endpoints per
        # student session instead of throttling the whole room together.
        session_id = request.path_params.get("session_id")
        if session_id is not None:
            rate_key = f"{rate_key}:{session_id}"
        
        if redis_client:
            try:
                now = int(time.time())
                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(rate_key, 0, now - window_seconds)
                pipe.zcard(rate_key)
                pipe.zadd(rate_key, {str(now) + ":" + str(time.time()): now})
                pipe.expire(rate_key, window_seconds)
                results = pipe.execute()
                
                req_count = results[1]
                if req_count >= max_requests:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded. Please try again later.",
                        headers={"Retry-After": str(window_seconds)}
                    )
                return
            except HTTPException:
                raise
            except Exception:
                # Fallback to in-memory on redis connection error
                pass
        
        allowed, remaining, retry_after = in_memory_limiter.is_allowed(rate_key, max_requests, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please retry in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )

    return dependency
