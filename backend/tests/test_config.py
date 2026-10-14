import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "raw", ["proofcard-x-proofs", "gs://proofcard-x-proofs", " gs://proofcard-x-proofs/ "]
)
def test_proof_bucket_accepts_gs_uri(raw: str) -> None:
    # E04 prints the bucket as gs://name; the storage client needs the bare name.
    assert Settings(_env_file=None, proof_bucket=raw).proof_bucket == "proofcard-x-proofs"


def test_proof_bucket_empty_stays_empty() -> None:
    assert Settings(_env_file=None).proof_bucket == ""
