import math
import time

from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

GLOBAL_KEY = "everyone"


class RateLimiter:
    """Per-client and global request limits, kept in memory (the Space runs one process)."""

    def __init__(self, per_client: str, overall: str):
        self.strategy = MovingWindowRateLimiter(MemoryStorage())
        self.per_client = parse_many(per_client)
        self.overall = parse_many(overall)

    def hit(self, client: str) -> int | None:
        """Count a request. Returns seconds to wait if it's over a limit (and not counted)."""
        checks = [(limit, client) for limit in self.per_client]
        checks += [(limit, GLOBAL_KEY) for limit in self.overall]
        # Test everything before counting anything, so a rejected request uses no quota.
        for limit, key in checks:
            if not self.strategy.test(limit, key):
                reset = self.strategy.get_window_stats(limit, key).reset_time
                return max(1, math.ceil(reset - time.time()))
        for limit, key in checks:
            self.strategy.hit(limit, key)
        return None
