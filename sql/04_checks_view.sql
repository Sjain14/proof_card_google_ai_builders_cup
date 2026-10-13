-- 04 · ALTERED checks (Telegram bot + web upload). Source: extension table checks_raw_latest.
-- No chat ids or user ids are stored in checks docs (privacy by design), only outcome data.
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.checks` AS
SELECT
  document_id                                         AS check_id,
  JSON_VALUE(data, '$.card_id')                       AS card_id,
  JSON_VALUE(data, '$.channel')                       AS channel,   -- telegram | web
  JSON_VALUE(data, '$.result')                        AS result,    -- VERIFIED | ALTERED | UNKNOWN
  SAFE_CAST(JSON_VALUE(data, '$.text_similarity') AS FLOAT64) AS text_similarity,
  SAFE_CAST(JSON_VALUE(data, '$.phash_distance') AS INT64)    AS phash_distance,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%E*S%Ez', JSON_VALUE(data, '$.created_at')) AS created_at
FROM `{{PROJECT}}.proofcard_raw.checks_raw_latest`;
