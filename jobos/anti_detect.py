"""Centralized anti-detection utilities for browser automation.

Provides human-like delays, typing simulation, mouse movement,
viewport randomization, and session management to avoid detection
by BOSS Zhipin's anti-bot systems.
"""

import random
import time
from datetime import datetime, timezone, timedelta


# China timezone offset
CHINA_TZ = timezone(timedelta(hours=8))

# Realistic Chrome user agents (Windows/Mac/Linux Chrome 120+)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# Viewport presets that look like real screens
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1600, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 1680, "height": 1050},
    {"width": 1280, "height": 800},
]


def human_delay(min_sec=2.0, max_sec=5.0):
    """Sleep a random duration between min and max seconds.

    Uses a beta distribution to favor values near the middle,
    avoiding suspiciously uniform timing patterns.
    """
    # Beta distribution clusters around 0.4-0.6 of the range
    alpha, beta = 2, 2
    ratio = random.betavariate(alpha, beta)
    delay = min_sec + ratio * (max_sec - min_sec)
    # Add small gaussian jitter
    delay += random.gauss(0, 0.15)
    delay = max(min_sec * 0.8, min(max_sec * 1.1, delay))
    time.sleep(delay)
    return delay


def typing_delay():
    """Delay between keystrokes, simulating real typing speed.

    Real typing speed: 80-120ms per character for Chinese input.
    """
    return random.uniform(50, 150) / 1000


async def simulate_typing(page, selector, text):
    """Type text character by character with human-like delays.

    Uses Playwright's type() with per-keystroke delays instead of fill().
    Also adds occasional pauses to simulate thinking.
    """
    element = page.locator(selector).first
    await element.click()
    human_delay(0.3, 0.8)  # Click-to-type pause

    for i, char in enumerate(text):
        await page.keyboard.type(char, delay=typing_delay() * 1000)
        # Occasional longer pause (simulating thought)
        if random.random() < 0.05:
            human_delay(0.5, 1.5)


def simulate_typing_sync(page, selector, text):
    """Synchronous version of typing simulation."""
    element = page.locator(selector).first
    element.click()
    human_delay(0.3, 0.8)

    for char in text:
        page.keyboard.type(char, delay=int(typing_delay() * 1000))
        if random.random() < 0.05:
            human_delay(0.5, 1.5)


async def simulate_mouse_move(page, target_x, target_y, steps=None):
    """Move mouse to target with curved, human-like trajectory.

    Adds random waypoints between start and end to create
    a non-linear path that looks natural.
    """
    if steps is None:
        steps = random.randint(3, 8)

    # Get current mouse position (or random start)
    start_x = random.randint(100, 800)
    start_y = random.randint(100, 600)

    for i in range(steps):
        ratio = (i + 1) / steps
        # Add curve via sine wave offset
        curve_offset = random.gauss(0, 20)
        x = int(start_x + (target_x - start_x) * ratio + curve_offset * (1 - ratio))
        y = int(start_y + (target_y - start_y) * ratio + random.gauss(0, 10))
        await page.mouse.move(x, y)
        human_delay(0.02, 0.08)


def random_viewport():
    """Return a randomized viewport size based on common screen resolutions."""
    base = random.choice(VIEWPORTS)
    # Add small random variation (±5%)
    w = base["width"] + random.randint(-30, 30)
    h = base["height"] + random.randint(-20, 20)
    return {"width": w, "height": h}


def random_user_agent():
    """Return a random realistic Chrome user-agent string."""
    return random.choice(USER_AGENTS)


def is_business_hours():
    """Check if current time is within typical business hours in China (8:00-22:00)."""
    now = datetime.now(CHINA_TZ)
    return 8 <= now.hour < 22


def is_active_hours():
    """Check if current time is within active job-seeking hours (9:00-21:00)."""
    now = datetime.now(CHINA_TZ)
    return 9 <= now.hour < 21


def get_context_options():
    """Return a dict of browser context options with anti-detection settings."""
    return {
        "viewport": random_viewport(),
        "user_agent": random_user_agent(),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "geolocation": {
            "latitude": 22.27 + random.uniform(-0.1, 0.1),
            "longitude": 113.57 + random.uniform(-0.1, 0.1),
        },
        "permissions": ["geolocation"],
        "extra_http_headers": {
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    }


class DailyRateLimiter:
    """Track and enforce daily action limits to avoid triggering rate limits."""

    def __init__(self, max_submissions=20, max_replies=30, state_file=None):
        self.max_submissions = max_submissions
        self.max_replies = max_replies
        self.state_file = state_file
        self._load()

    def _load(self):
        if self.state_file and self.state_file.exists():
            import json
            data = json.loads(self.state_file.read_text())
            self.today = data.get("date", "")
            self.submissions = data.get("submissions", 0)
            self.replies = data.get("replies", 0)
        else:
            self.today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")
            self.submissions = 0
            self.replies = 0

    def _save(self):
        if self.state_file:
            import json
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({
                "date": self.today,
                "submissions": self.submissions,
                "replies": self.replies,
            }, indent=2))

    def _check_day(self):
        today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")
        if today != self.today:
            self.today = today
            self.submissions = 0
            self.replies = 0

    def can_submit(self):
        self._check_day()
        return self.submissions < self.max_submissions

    def can_reply(self):
        self._check_day()
        return self.replies < self.max_replies

    def record_submission(self):
        self._check_day()
        self.submissions += 1
        self._save()

    def record_reply(self):
        self._check_day()
        self.replies += 1
        self._save()
