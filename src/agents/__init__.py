"""Agent modules. Each agent owns one data domain, calls deterministic tools,
optionally annotates its finding with a grounded LLM rationale, and hands off a
structured finding to the next agent via the coordinator."""
