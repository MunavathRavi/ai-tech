import os
LLM_MODE = os.getenv("LLM_MODE", "live")
FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-5-5")
SMART_MODEL = os.getenv("SMART_MODEL", "claude-sonnet-5-5")
# Which model each agent uses. Change via env, then let evals/run_evals.py prove the choice with numbers.
AGENT_MODELS = {
    "extractor": os.getenv("EXTRACTOR_MODEL", FAST_MODEL),
    "clarifier": os.getenv("CLARIFIER_MODEL", SMART_MODEL),
    "estimator": os.getenv("ESTIMATOR_MODEL", SMART_MODEL),
    "reviewer":  os.getenv("REVIEWER_MODEL", SMART_MODEL),
    "writer":    os.getenv("WRITER_MODEL", FAST_MODEL),
}
BRAIN_URL = os.getenv("BRAIN_URL", "http://localhost:8001")
BRAIN_API_KEY = os.getenv("BRAIN_API_KEY", "")
DATA_DIR = os.getenv("DATA_DIR", "data/projects")
HOURLY_RATE = float(os.getenv("HOURLY_RATE", "50"))
PRICES = {
    FAST_MODEL: (float(os.getenv("FAST_IN", "1.0")), float(os.getenv("FAST_OUT", "5.0"))),
    SMART_MODEL: (float(os.getenv("SMART_IN", "3.0")), float(os.getenv("SMART_OUT", "15.0"))),
}
