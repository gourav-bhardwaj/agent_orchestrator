from prometheus_client import Counter, Histogram
from prometheus_client import CollectorRegistry
registry = CollectorRegistry()

LLM_REQUESTS = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["model", "agent"],
    registry=registry
)

LLM_COST = Counter(
    "llm_cost_usd_total",
    "Total LLM cost in USD",
    ["model", "agent"],
    registry=registry
)

INPUT_TOKENS = Counter(
    "llm_input_tokens_total",
    "Total input tokens",
    ["model", "agent"],
    registry=registry
)

OUTPUT_TOKENS = Counter(
    "llm_output_tokens_total",
    "Total output tokens",
    ["model", "agent"],
    registry=registry
)

LLM_ERRORS = Counter(
    "llm_errors_total",
    "Total LLM errors",
    ["model", "agent"],
    registry=registry
)

LLM_LATENCY = Histogram(
    "llm_request_duration_seconds",
    "LLM execution latency",
    ["model", "agent"],
    registry=registry
)