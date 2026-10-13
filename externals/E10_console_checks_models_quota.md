# E10 · Console checks: model in region, grounding, quota

**Deadline:** 15 Oct · **Needs:** E03, E04.

The code reads the model id from `PC_GEMINI_MODEL` (default `gemini-2.5-flash`), so a change is config, not code.

## Steps
1. Vertex AI → Model Garden → search Gemini. Note the newest **Flash** model available in your region. Docs: ✅ [Gemini models on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/models) and ✅ [Locations](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations).
2. Vertex AI Studio → open a prompt with that model, turn on **Grounding: Google Search**, ask "What is the current petrol price in Delhi?" and check it returns sources ✅ [Grounding with Google Search](https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search).
3. IAM & Admin → Quotas → filter "Generate content requests per minute" for that model + region. Note the number. Prebunk fires about 15 calls per brief, so anything ≥ 60/min is fine 🟡.
4. Optional: Speech-to-Text → try 1 minute of the demo clip with language `hi-IN` to see Hinglish quality (fallback path for the live bridge).

## What to hand Agent
One DM line: model id, region, RPM quota, grounding worked yes/no.

## Done when
Line sent. If the chosen model isn't in `asia-south1`, also send which region it is in; the backend has a separate `PC_GEMINI_REGION`.
