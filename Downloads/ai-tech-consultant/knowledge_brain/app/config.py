import os

DB_PATH = os.getenv("BRAIN_DB", "brain.db")
SITEMAP_URL = os.getenv("SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml")
LLM_MODE = os.getenv("LLM_MODE", "live")          # "live" or "mock" (offline, deterministic)
FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-5-5")
SMART_MODEL = os.getenv("SMART_MODEL", "claude-sonnet-5-5")
API_KEY = os.getenv("BRAIN_API_KEY", "")          # empty = auth disabled (local dev)

# Politeness: the first full read must not hurt the help center's server.
CRAWL_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENCY", "2"))
CRAWL_MIN_DELAY_S = float(os.getenv("CRAWL_MIN_DELAY_S", "1.0"))   # global gap between requests
CRAWL_MAX_RETRIES = int(os.getenv("CRAWL_MAX_RETRIES", "4"))
MAX_IMAGES_PER_PAGE = int(os.getenv("MAX_IMAGES_PER_PAGE", "6"))
SYNC_INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "24"))  # 0 disables scheduler

# Price per million tokens (input, output). Override via env; used only for cost reporting.
PRICES = {
    FAST_MODEL: (float(os.getenv("FAST_IN", "1.0")), float(os.getenv("FAST_OUT", "5.0"))),
    SMART_MODEL: (float(os.getenv("SMART_IN", "3.0")), float(os.getenv("SMART_OUT", "15.0"))),
}
