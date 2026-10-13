-- 03 · typed claims across all sessions. Source: extension table claims_raw_latest
-- (collection group "claims", configured with wildcard path sessions/{sid}/claims).
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.claims` AS
SELECT
  document_id                                     AS claim_id,
  REGEXP_EXTRACT(document_name, r'sessions/([^/]+)/claims') AS session_id,
  JSON_VALUE(data, '$.text')                      AS text,
  JSON_VALUE(data, '$.lang')                      AS lang,
  JSON_VALUE(data, '$.source')                    AS source,      -- predicted | live
  JSON_VALUE(data, '$.status')                    AS status,      -- queued | checking | proved | failed
  JSON_VALUE(data, '$.verdict')                   AS verdict,
  JSON_VALUE(data, '$.card_id')                   AS card_id,
  JSON_VALUE(data, '$.matched_claim_id')          AS matched_claim_id, -- live claim that hit a prebunked one
  SAFE_CAST(JSON_VALUE(data, '$.latency_ms') AS INT64) AS latency_ms,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%E*S%Ez', JSON_VALUE(data, '$.created_at')) AS created_at
FROM `{{PROJECT}}.proofcard_raw.claims_raw_latest`;
