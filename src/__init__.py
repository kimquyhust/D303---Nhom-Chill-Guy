"""Multi-agent E-commerce Dispute Resolution system (K4 Day 09).

Package layout:
  config.py       -> runtime configuration, model + provider settings, thresholds
  data_store.py   -> deterministic tool layer over the 9 Olist CSVs
  llm.py          -> LLM client abstraction (ollama / groq / openai-compatible / deterministic)
  trace.py        -> JSONL trace logger for a real run
  schema.py       -> output builders, rounding, array-limit enforcement
  agents/         -> one module per agent (customer, order_product, payment, delivery,
                     policy, verifier) plus the coordinator that orchestrates handoffs
"""
