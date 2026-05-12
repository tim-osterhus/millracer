from millracer.decision import Decision, parse_decision


def test_parse_decision_reads_fenced_json() -> None:
    raw = """
    Here is the decision:

    ```json
    {
      "decision": "millrace",
      "intake_kind": "probe",
      "why": "multi-stage",
      "mode": "learning_pi",
      "signals": ["large pre-existing codebase", "uncertain affected files"]
    }
    ```
    """

    assert parse_decision(raw) == Decision(
        route="millrace",
        why="multi-stage",
        mode="learning_pi",
        intake_kind="probe",
        signals=("large pre-existing codebase", "uncertain affected files"),
    )


def test_parse_decision_preserves_custom_loop_signal() -> None:
    raw = (
        '{"decision": "millrace", "why": "needs a special topology", '
        '"custom_loop_needed": true, "notes": "use a custom loop"}'
    )

    decision = parse_decision(raw)

    assert decision.custom_loop_needed is True
    assert decision.notes == "use a custom loop"


def test_parse_decision_falls_back_to_direct_when_output_is_unstructured() -> None:
    decision = parse_decision("decision: direct\nwhy: small edit")

    assert decision.route == "direct"
    assert decision.why == "small edit"
    assert decision.mode == "default_pi"


def test_parse_decision_normalizes_invalid_intake_to_none() -> None:
    decision = parse_decision(
        '{"decision": "millrace", "intake_kind": "whatever", "why": "multi-stage"}'
    )

    assert decision.intake_kind is None
