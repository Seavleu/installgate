def test_contracts_import() -> None:
    from contracts.contracts import Verdict

    assert Verdict.ALLOW.value == "ALLOW"
