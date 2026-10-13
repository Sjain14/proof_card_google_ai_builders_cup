-- 05 · metrics for the deck and the benchmark slide. Report these numbers as measured,
-- never rounded up.

-- Verdict mix of issued cards.
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.m_verdict_mix` AS
SELECT verdict, COUNT(*) AS cards, ROUND(AVG(support_score), 3) AS avg_support
FROM `{{PROJECT}}.proofcard_analytics.cards`
GROUP BY verdict;

-- Prebunk hit rate per session: share of live claims that matched a prebunked claim
-- (instant card, no model call on the hot path).
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.m_prebunk_hit_rate` AS
SELECT
  session_id,
  COUNTIF(source = 'live') AS live_claims,
  COUNTIF(source = 'live' AND matched_claim_id IS NOT NULL) AS instant_hits,
  SAFE_DIVIDE(COUNTIF(source = 'live' AND matched_claim_id IS NOT NULL), COUNTIF(source = 'live')) AS hit_rate
FROM `{{PROJECT}}.proofcard_analytics.claims`
GROUP BY session_id;

-- Live latency: instant (prebunk hit) vs cold (live check), p50 / p90 in ms.
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.m_latency` AS
SELECT
  IF(matched_claim_id IS NOT NULL, 'instant', 'cold') AS path,
  COUNT(*) AS n,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(50)] AS p50_ms,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(90)] AS p90_ms
FROM `{{PROJECT}}.proofcard_analytics.claims`
WHERE source = 'live' AND latency_ms IS NOT NULL
GROUP BY path;

-- ALTERED checks by channel and outcome.
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.m_checks` AS
SELECT channel, result, COUNT(*) AS checks
FROM `{{PROJECT}}.proofcard_analytics.checks`
GROUP BY channel, result;
