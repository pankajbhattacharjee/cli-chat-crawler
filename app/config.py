"""Central configuration (env-driven, safe defaults)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CLI_PATH = ROOT / "cli" / "sitecrawl.py"
RUNS_DIR = ROOT / "runs"
STATIC_DIR = ROOT / "static"
RUNS_DIR.mkdir(exist_ok=True)

MAX_PAGES_CAP = int(os.getenv("MAX_PAGES_CAP", "30"))
MAX_DEPTH_CAP = int(os.getenv("MAX_DEPTH_CAP", "2"))
CRAWL_TIME_BUDGET = int(os.getenv("CRAWL_TIME_BUDGET_SEC", "45"))
HARD_KILL_GRACE = 15          # seconds after the CLI's own budget before SIGKILL
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_CRAWLS", "2"))
MAX_OUTPUT_BYTES = 5_000_000  # result JSON size cap
MAX_LOG_LINES = 500
DEV_ALLOW_PRIVATE = os.getenv("DEV_ALLOW_PRIVATE_HOSTS", "0") == "1"

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# LLM provider: auto (Gemini key -> Gemini, else Anthropic key -> Claude, else rules),
# or force one of: gemini | anthropic | rules
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_REQUESTS_PER_DAY = int(os.getenv("MAX_REQUESTS_PER_DAY", "300"))  # global cap: protects your API quota
# AWS S3 Storage
S3_ENABLED = os.getenv("S3_ENABLED", "0").strip() == "1"
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1").strip()
