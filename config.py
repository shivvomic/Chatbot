"""Single home for settings, model names, thresholds and paths.

Two kinds of values live here:
  * `settings` - deployment values read from the environment / .env (provider, API keys,
    CORS origins ...). Validated by pydantic-settings.
  * module constants - tuning knobs (top_k, thresholds, chunk sizes). Change them here only;
    no other module hardcodes a number.
"""
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).parent


class Settings(BaseSettings):
    """Environment-driven settings. Every field is documented in .env.example."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    llm_provider: Literal["gemini", "openai", "groq"] = "gemini"
    llm_model: str = ""  # empty -> provider default from LLM_MODELS
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None

    api_keys: SecretStr = SecretStr("")  # "key1:customer,key2:employee,key3:admin"
    cors_origins: str = "http://localhost:8501"  # comma-separated
    api_url: str = "http://localhost:8000"  # used by the Streamlit UI
    log_level: str = "INFO"


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:  # fail fast with a readable message, never echo values
        fields = ", ".join(str(e["loc"][0]).upper() for e in exc.errors())
        raise SystemExit(f"Invalid environment configuration for: {fields}. See .env.example.") from None


settings = _load_settings()


def require(*names: str) -> None:
    """Exit with a clear message if any of the named settings (env var names) is empty."""
    missing = []
    for name in names:
        value = getattr(settings, name.lower())
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw:
            missing.append(name)
    if missing:
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}. See .env.example.")


# --- Paths ---
DATASET_DIR = ROOT / "hcl_dataset"
DOCS_DIR = DATASET_DIR / "documents"
METADATA_PATH = DATASET_DIR / "metadata" / "documents_metadata.json"
RELATIONSHIPS_PATH = DATASET_DIR / "metadata" / "relationships.json"
SENSITIVE_REGISTER_PATH = DATASET_DIR / "metadata" / "sensitive_items_register.json"
QUESTIONS_PATH = DATASET_DIR / "questions" / "questions.jsonl"
QRELS_PATH = DATASET_DIR / "questions" / "qrels.csv"
DATA_DIR = ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_METADATA_PATH = UPLOADS_DIR / "metadata.json"
EVAL_DIR = ROOT / "eval"

# --- LLM provider (swap with the LLM_PROVIDER env var) ---
LLM_PROVIDER = settings.llm_provider
LLM_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-4o-mini",
    "groq": "openai/gpt-oss-120b",
}
LLM_MODEL = settings.llm_model or LLM_MODELS[LLM_PROVIDER]
LLM_TIMEOUT_S = 60
LLM_TEMPERATURE = 0.0
LLM_RETRIES = 2  # extra attempts on HTTP 429 / 5xx (rate limits, provider overload)
LLM_RETRY_BACKOFF_S = 2.0  # wait before retry n is backoff * n, unless the provider sends Retry-After
LLM_RETRY_MAX_WAIT_S = 20.0  # never sleep longer than this for one retry
SCOPE_LLM_TIMEOUT_S = 15  # the scope classifier is a quick yes/no; don't let it stall a request


def llm_api_key(provider: str) -> str:
    """API key for `provider`, or a clear error naming the env var to set."""
    secret = getattr(settings, f"{provider}_api_key", None)
    if not secret or not secret.get_secret_value():
        raise RuntimeError(f"{provider.upper()}_API_KEY is not set (LLM_PROVIDER={provider})")
    return secret.get_secret_value()


# --- Embedding / reranking models ---
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-base"

# --- Roles / access control: a role reads every level whose rank <= its own rank ---
ACCESS_RANK = {"public": 0, "internal": 1, "admin": 2}
ROLE_RANK = {"customer": 0, "employee": 1, "admin": 2}

# --- Chunking / redaction ---
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
CHUNK_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 50
TOKENS_PER_WORD = 1.3  # rough estimate; we count whitespace words, not model tokens
HEADING_SEPARATOR = " > "
REDACTION_PATTERNS = {
    "EMAIL": r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    "PHONE": r"\+\d{1,3}[-\s.]\d{3}[-\s.]\d{4}\b|\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",
    "TOKEN": r"\b[A-Z]{2,}-[A-Z]{2,}-[0-9A-F]{12,}\b|\b[A-Z]{2,}-VAULT-\d+\b",
}

# --- Index ---
CHROMA_DIR = DATA_DIR / "chroma"
CHROMA_COLLECTION = "chunks"
BM25_PATH = DATA_DIR / "bm25.pkl"
EMBED_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBED_BATCH_SIZE = 32

# --- Search ---
RETRIEVE_TOP_K = 20  # candidates per retriever (vector, BM25)
RRF_K = 60
RERANK_TOP_N = 6
SEARCH_MODES = ("bm25", "vector", "hybrid", "hybrid_rerank")  # ablation; default is the last

# --- Context expansion (step 6) ---
CONTEXT_MAX_TOKENS = 2000  # cap on the evidence sent to the LLM
EXPAND_NEIGHBORS_TOP_N = 2  # add prev/next chunks for this many top hits
EXPAND_REFERENCES_TOP_N = 3  # follow `references` for this many top hits
STALE_STATUSES = ("superseded", "stale", "unofficial")  # tagged in the prompt

# --- Guardrails (step 7) ---
# Regexes (case-insensitive) that mark a question or a document line as an instruction attack.
INJECTION_PATTERNS = (
    r"\b(ignore|disregard|forget|override)\b[^.]{0,30}\b(previous|prior|above|earlier|all)\b[^.]{0,20}\b(instructions?|rules|prompts?)\b",
    r"\bsystem (prompt|message|note)\b",
    r"\bdeveloper (mode|message)\b",
    r"\byou are now\b|\bpretend (to be|you are)\b|\bjailbreak\b",
    r"\bi am (the|an?|your) (ceo|cto|admin|administrator|owner|boss|manager)\b",
    r"\bi (authori[sz]e|permit|allow) you\b",
    r"\b(print|show|dump|reveal)\b[^.]{0,20}\b(full|entire|whole|all)\b[^.]{0,10}\b(contents?|text|document|runbook)\b",
    r"\breveal\b[^.]{0,40}\bpassword\b",
)
# Requests for a credential value (not questions about password *rules*) are always refused.
SECRET_REQUEST_PATTERN = (
    r"\b(what is|what's|tell me|give me|show( me)?|reveal|print|share)\b[^?.]{0,40}"
    r"\b(password|passcode|secret|api key|token|credentials?)\b(?!\s*(reset|polic|rule|length|requirement|expir))"
)
OUT_OF_SCOPE_KEYWORDS = (
    "weather", "forecast", "stock price", "recipe", "football", "cricket", "horoscope",
    "movie", "song", "joke", "poem", "lottery", "election",
)
OOS_MIN_DOMAIN_WORDS = 1  # fewer domain words than this -> ask the LLM if it is in scope
RESTRICTED_MIN_SCORE = 0.5  # unfiltered best match must be at least this relevant ...
RESTRICTED_WEAK_SCORE = 0.1  # ... and the role's own best match below this -> refuse

# --- Confidence gate (step 8; tune with eval/tune_thresholds.py) ---
# Top rerank score below this -> not_found, no LLM call.
# Tuned on questions.jsonl: gated not_found questions score <= 0.017, answerable ones >= 0.033.
NOT_FOUND_THRESHOLD = 0.025
VAGUE_MAX_CONTENT_WORDS = 2  # questions with this few content words are too vague
CLARIFY_MAX_CONTENT_WORDS = 4  # short questions are checked for "several unrelated topics"
CLARIFY_SCORE_MARGIN = 0.1  # hits within this margin of the top hit count as "close"
CLARIFY_MIN_SCORE = 0.3  # ... and only strong hits count: near-zero noise scores are always "close"
CLARIFY_MIN_TOPICS = 3  # this many close, unrelated documents -> needs_clarification
CLARIFY_OPTIONS = 3  # options listed in the clarifying question

# --- Generation / verification (steps 9-11) ---
LLM_JSON_RETRIES = 1  # extra attempts when the reply is not valid JSON
VERIFY_REGENERATIONS = 1  # extra attempts when verification fails
EXCERPT_CHARS = 240  # citation excerpt length
CONFLICT_MIN_SCORE = 0.5  # hits from different docs at least this relevant are conflict candidates

# --- API (phase B) ---
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
REQUEST_MAX_BYTES = UPLOAD_MAX_BYTES + 64 * 1024  # body limit, slightly above the upload limit
UPLOAD_EXTENSIONS = {".pdf": "pdf", ".html": "html", ".htm": "html", ".md": "md", ".markdown": "md", ".txt": "txt"}
RATE_LIMIT_PER_MINUTE = 30  # per API key
QUESTION_MAX_CHARS = 1000
# The UI must wait longer than the pipeline's worst case: up to 4 answer calls
# ((1 + LLM_JSON_RETRIES) * (1 + VERIFY_REGENERATIONS)) plus the scope check.
UI_REQUEST_TIMEOUT_S = 300

# --- Evaluation (phase C) ---
EVAL_RESULTS_PATH = EVAL_DIR / "results.json"
EVAL_REPORT_PATH = EVAL_DIR / "REPORT.md"
EVAL_RECALL_KS = (1, 3, 5)
