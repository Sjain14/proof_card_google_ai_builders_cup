def test_short_forward_with_several_claims_is_split() -> None:
    from app.main import several_claims

    fwd = (
        "Forwarded as received: India is now the world's fourth largest economy. "
        "Petrol is cheapest in India among all G20 countries. "
        "Every village in India got electricity in 2018. Share before they delete!!"
    )
    assert several_claims(fwd)
    assert not several_claims("India has 22 languages in the Eighth Schedule of the Constitution")
