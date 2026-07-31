# litellm/

**Populated by:** Phase 10 — LLM gateway bring-up

This directory will contain the LiteLLM Proxy configuration (spec §20).

**Key file:** `config.yaml` — provider priority, fallback chain, per-task routing, caching config.

**Provider fallback chain (§20):**
1. DeepSeek (primary)
2. Anthropic (Claude)
3. OpenAI (ChatGPT)
4. Local model (last resort — left unspecified per SPEC_CLARIFICATIONS #12; skip until needed)

**Model tiering (§20.1):**
- Cheapest tier: routine filler, ambient events (§16), BetaCorp flavor news
- Mid tier: weekly digest (§12.3)
- Heavier tier: meetings, meeting-derived content, anything reacting to the Principal

**Token-efficiency requirements (§20.1):**
1. Cache static prefix (system instructions + persona + JSON schema + company direction) —
   byte-identical across calls; enable DeepSeek/Anthropic prompt caching in LiteLLM.
2. Vary only the small tail (the specific dynamic content per call).
3. Compact memory: only thread summary + last 1-2 events, never full history.

**Network placement:** `net_llm_bridge` — its ONLY external route. No other network gets
internet access through it.

**API keys:** via env vars only (see `.env.example`). Keys NEVER written in this config file.

**Dependencies:** Phase 1 (Compose topology).
