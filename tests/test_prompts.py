from millracer.prompts import (
    MILLRACER_SYSTEM_PROMPT,
    decision_prompt,
    finalization_prompt,
)

FORBIDDEN_PROMPT_TERMS = (
    "EvoClaw",
    "hidden eval",
    "hidden evaluation",
    "milestone",
    "scoreboard",
    "benchmark",
)


def test_system_prompt_explains_generic_intake_kind_selection() -> None:
    prompt = MILLRACER_SYSTEM_PROMPT.lower()

    assert "route and intake kind" in prompt
    assert "large pre-existing codebase" in prompt
    assert "probe when in doubt" in prompt
    assert "probe means investigate before implementation" in prompt
    assert "task is only for tightly scoped execution-ready work" in prompt
    assert "idea is for clear outcomes" in prompt


def test_decision_prompt_requests_intake_kind_and_generic_signals() -> None:
    prompt = decision_prompt("Change runtime behavior")

    assert '"intake_kind": "probe|idea|task"' in prompt
    assert '"signals": ["<short generic signal>", "..."]' in prompt
    assert "In a large pre-existing codebase, choose probe when in doubt." in prompt


def test_finalization_prompt_reports_intake_kind_and_scope() -> None:
    prompt = finalization_prompt(
        task="Do one scoped item.",
        workspace="/tmp/ws",
        route="millrace",
        intake_kind="probe",
        outcome="completed",
        scoped_completion=True,
        completion_evidence_json='[{"kind": "arbiter_complete"}]',
        event_kind="complete",
        event_reason="done",
        status_json="{}",
        scoped_work_json='{"item_id": "ITEM-123"}',
    )

    assert "- route: millrace" in prompt
    assert "- intake kind: probe" in prompt
    assert "- outcome: completed" in prompt
    assert "- scoped completion: True" in prompt
    assert '[{"kind": "arbiter_complete"}]' in prompt
    assert '{"item_id": "ITEM-123"}' in prompt


def test_injected_prompts_avoid_forbidden_benchmark_specific_terms() -> None:
    prompts = (
        MILLRACER_SYSTEM_PROMPT,
        decision_prompt("Change runtime behavior"),
        finalization_prompt(
            task="Do one scoped item.",
            workspace="/tmp/ws",
            route="millrace",
            intake_kind="probe",
            outcome="completed",
            scoped_completion=True,
            completion_evidence_json='[{"kind": "arbiter_complete"}]',
            event_kind="complete",
            event_reason="done",
            status_json="{}",
        ),
    )

    for prompt in prompts:
        for term in FORBIDDEN_PROMPT_TERMS:
            assert term.lower() not in prompt.lower()
