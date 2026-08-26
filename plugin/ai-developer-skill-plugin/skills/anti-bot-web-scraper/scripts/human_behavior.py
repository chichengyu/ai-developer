"""Human-like request behavior: UA rotation and randomized pacing."""

from __future__ import annotations

import random
import time

DEFAULT_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
)


class HumanBehavior:
    """Rotates user agents and sleeps with human-like random pacing."""

    def __init__(
        self,
        user_agents: list[str] | tuple[str, ...] | None = None,
        *,
        min_delay: float = 0.2,
        max_delay: float = 1.2,
        jitter: float = 0.3,
        seed: int | None = None,
    ) -> None:
        self.user_agents = tuple(user_agents) if user_agents else DEFAULT_USER_AGENTS
        self.min_delay = max(0.0, float(min_delay))
        self.max_delay = max(self.min_delay, float(max_delay))
        self.jitter = max(0.0, float(jitter))
        self._random = random.Random(seed)
        self._index = 0

    def next_user_agent(self) -> str:
        value = self.user_agents[self._index % len(self.user_agents)]
        self._index += 1
        return value

    def delay(self) -> float:
        base = self._random.uniform(self.min_delay, self.max_delay)
        return max(0.0, base + self._random.uniform(-self.jitter, self.jitter))

    def sleep_like_human(self) -> float:
        delay = self.delay()
        time.sleep(delay)
        return delay

    def backoff_delay(self, attempt: int, base: float = 0.5, maximum: float = 30.0) -> float:
        delay = min(maximum, base * (2**attempt)) + self._random.uniform(0.0, self.jitter)
        time.sleep(delay)
        return delay


if __name__ == "__main__":
    behavior = HumanBehavior(seed=1)
    print(behavior.next_user_agent())
