from datetime import datetime, timedelta
import functools

def cache_ttl(ttl: int):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            cache_attr = f"_{func.__name__}_cache"
            expiry_attr = f"_{func.__name__}_expiry"
            
            if hasattr(self, expiry_attr) and datetime.now() < getattr(self, expiry_attr):
                return getattr(self, cache_attr)
                
            result = await func(self, *args, **kwargs)
            setattr(self, cache_attr, result)
            setattr(self, expiry_attr, datetime.now() + timedelta(seconds=ttl))
            return result
        return wrapper
    return decorator
