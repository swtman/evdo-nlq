# ADR-011: Ollama as the Local LLM Provider

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** @manoliss

## Context

The system currently requires a cloud LLM API key (Anthropic or Google).
Adding a local-LLM path serves two goals: (1) a fallback for users without
a key who want to see the app run end-to-end; (2) an eval-harness track
comparing cloud vs. local SPARQL generation quality. The `LLMProvider`
protocol was designed to make adding providers trivial.

## Options considered

### Option A — Ollama
- Pros: simple HTTP API; official Docker image; one-command model pull;
  `.env.example` already hinted at it (`OLLAMA_BASE_URL`); broad model
  compatibility (Qwen2.5, Llama 3, Phi-3, etc.); active maintenance.
- Cons: CPU-only inference is slow for 7B+ models; GPU passthrough
  requires additional setup on Windows/WSL2.

### Option B — llama.cpp server
- Pros: fine-grained GGUF quantization control; lowest memory footprint.
- Cons: no official Docker image; manual model download and GGUF
  conversion; more complex setup for recipients.

### Option C — text-generation-inference (TGI)
- Pros: production-grade, HuggingFace ecosystem.
- Cons: heavy image (several GB); CUDA-centric; significant overhead for
  a thesis demo context.

## Decision

We chose **Option A** (Ollama).

The `OllamaProvider` class implements the `LLMProvider` protocol
(`generate` + `stream`) using Ollama's `/api/generate` endpoint via
`httpx` (already available in the project via `fastapi[standard]`).
Usage counts come from `prompt_eval_count` and `eval_count` in Ollama's
response, matching the pattern used by Claude/Gemini providers.

**Default model for the compose stack:** `qwen2.5:3b-instruct` (~2 GB,
multilingual, CPU-feasible). Pulled automatically by `ollama-init` on
first launch. SPARQL generation quality is materially lower than cloud
providers for Greek-language ontology queries — this is documented in
the README and in the eval harness reports.

**Eval track:** users can `docker compose exec ollama ollama pull
qwen2.5:7b-instruct` (or 14b) for a stronger local model. No code
change needed.

## Consequences

- `OllamaProvider` is registered in `factory.py` under the `"ollama"` key.
- `GET /providers` checks Ollama reachability at request time (1-second
  timeout); the UI only shows Ollama when it is actually running.
- A new `Settings.ollama_base_url` field configures the endpoint.
- `httpx` is used for Ollama HTTP calls; it was already available but
  not yet imported in production code.
- Local-model SPARQL quality for Greek ontology queries is lower than
  cloud models — expected and documented, not a defect.

## Follow-ups

- [ ] Add Ollama section to README (fallback path + eval instructions)
- [ ] Run eval harness against qwen2.5:3b-instruct and include results in thesis
- [ ] Document GPU passthrough steps in README
