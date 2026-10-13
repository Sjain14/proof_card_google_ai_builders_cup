-- 01 · analytics dataset. The Firestore export extension writes its raw tables into
-- `proofcard_raw` (configured in externals/E15); views below live in proofcard_analytics.
CREATE SCHEMA IF NOT EXISTS `{{PROJECT}}.proofcard_analytics`
OPTIONS (location = 'asia-south1', description = 'Proof Card typed views and metrics');

CREATE SCHEMA IF NOT EXISTS `{{PROJECT}}.proofcard_raw`
OPTIONS (location = 'asia-south1', description = 'Firestore to BigQuery export (extension owned)');
