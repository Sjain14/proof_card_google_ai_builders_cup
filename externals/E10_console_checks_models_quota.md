# E10 · Console checks: model in region, grounding, quota

**Deadline:** 15 Oct · **Needs:** E03, E04.

The code reads the model id from `PC_GEMINI_MODEL` (default `gemini-3.5-flash` on the `global` endpoint; `gemini-2.5-flash` retires 20 Oct 2026, ✅ [model lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions)), so a change is config, not code. Live transcription runs on `PC_LIVE_REGION` (default `global`; `gemini-3.5-transcribe-live` is only in global / us / eu), embeddings on `PC_EMBED_REGION` (default = `PC_GCP_REGION`).

## Steps
1. Vertex AI → Model Garden → search Gemini. Note the newest **Flash** model available in your region. Docs: ✅ [Gemini models on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/models) and ✅ [Locations](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations).
2. Vertex AI Studio → open a prompt with that model, turn on **Grounding: Google Search**, ask "What is the current petrol price in Delhi?" and check it returns sources ✅ [Grounding with Google Search](https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search).
3. IAM & Admin → Quotas → filter "Generate content requests per minute" for that model + region. Note the number. Prebunk fires about 15 calls per brief, so anything ≥ 60/min is fine 🟡.
4. Live transcription: check the Gemini Live transcription model (`gemini-3.5-transcribe-live`, ✅ [Live transcription docs](https://ai.google.dev/gemini-api/docs/live-api/live-transcribe)) and `gemini-embedding-001` are offered in your region. If either is missing, note the region that has it; we set `PC_GEMINI_REGION` / `PC_EMBED_REGION` / `PC_LIVE_REGION` to match, no code change.
5. Optional: Speech-to-Text → try 1 minute of the demo clip with language `hi-IN` to see Hinglish quality (fallback path for the live bridge).

## What to hand Agent
One DM line: model id, region, RPM quota, grounding worked yes/no.

## Done when
Line sent. If the chosen model isn't in `asia-south1`, also send which region it is in; the backend has a separate `PC_GEMINI_REGION`.
