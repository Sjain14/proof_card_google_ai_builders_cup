-- 02 · typed cards. Source: extension table cards_raw_latest (collection path "cards").
CREATE OR REPLACE VIEW `{{PROJECT}}.proofcard_analytics.cards` AS
SELECT
  document_id                                              AS card_id,
  JSON_VALUE(data, '$.claim')                              AS claim,
  JSON_VALUE(data, '$.verdict')                            AS verdict,
  SAFE_CAST(JSON_VALUE(data, '$.support_score') AS FLOAT64) AS support_score,
  ARRAY_LENGTH(JSON_QUERY_ARRAY(data, '$.sources'))        AS source_count,
  JSON_VALUE(data, '$.card_sha256')                        AS card_sha256,
  SAFE_CAST(JSON_VALUE(data, '$.schema_version') AS INT64) AS schema_version,
  SAFE.PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%E*S%Ez', JSON_VALUE(data, '$.created_at')) AS created_at
FROM `{{PROJECT}}.proofcard_raw.cards_raw_latest`;
