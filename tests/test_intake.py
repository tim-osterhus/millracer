from millracer.decision import Decision
from millracer.intake import IntakeKind, choose_intake_kind


def test_large_preexisting_codebase_with_uncertain_surface_defaults_to_probe() -> None:
    decision = choose_intake_kind(
        "Update behavior in this large pre-existing codebase; affected files are uncertain.",
        requested=IntakeKind.AUTO,
        decision=None,
    )

    assert decision.intake_kind == IntakeKind.PROBE
    assert "large pre-existing codebase" in decision.signals


def test_broad_migration_defaults_to_probe() -> None:
    decision = choose_intake_kind(
        "Migrate the runtime configuration architecture across the repo.",
        requested=IntakeKind.AUTO,
        decision=None,
    )

    assert decision.intake_kind == IntakeKind.PROBE


def test_understand_before_changing_defaults_to_probe() -> None:
    decision = choose_intake_kind(
        "Need to understand the codebase before changing how the harness launches.",
        requested=IntakeKind.AUTO,
        decision=None,
    )

    assert decision.intake_kind == IntakeKind.PROBE


def test_clear_product_capability_defaults_to_idea() -> None:
    decision = choose_intake_kind(
        "Build a new operator dashboard capability for viewing queued runs.",
        requested=IntakeKind.AUTO,
        decision=None,
    )

    assert decision.intake_kind == IntakeKind.IDEA


def test_exact_file_and_failing_test_defaults_to_task() -> None:
    decision = choose_intake_kind(
        "Fix src/millracer/monitor.py so tests/test_monitor.py::test_idle passes.",
        requested=IntakeKind.AUTO,
        decision=None,
    )

    assert decision.intake_kind == IntakeKind.TASK


def test_forced_intake_overrides_auto_classification() -> None:
    task = "Update behavior in a large pre-existing codebase with uncertain affected files."

    assert (
        choose_intake_kind(task, requested=IntakeKind.TASK, decision=None).intake_kind
        == IntakeKind.TASK
    )
    assert (
        choose_intake_kind(task, requested=IntakeKind.IDEA, decision=None).intake_kind
        == IntakeKind.IDEA
    )
    assert (
        choose_intake_kind(task, requested=IntakeKind.PROBE, decision=None).intake_kind
        == IntakeKind.PROBE
    )


def test_decision_intake_is_used_when_auto_requested() -> None:
    decision = choose_intake_kind(
        "Create a new user-facing workflow.",
        requested=IntakeKind.AUTO,
        decision=Decision(
            route="millrace",
            why="needs planning",
            intake_kind="idea",
            signals=("clear outcome needing shaping",),
        ),
    )

    assert decision.intake_kind == IntakeKind.IDEA
    assert decision.signals == ("clear outcome needing shaping",)


def test_malformed_or_missing_intake_falls_back_to_conservative_probe() -> None:
    decision = choose_intake_kind(
        "Adjust the runtime based on the attached issue.",
        requested=IntakeKind.AUTO,
        decision=Decision(route="millrace", why="unstructured"),
    )

    assert decision.intake_kind == IntakeKind.PROBE
