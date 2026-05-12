from millracer.cli import _parser


def test_run_parser_accepts_intake_and_terminal_stage_toggle() -> None:
    args = _parser().parse_args(
        [
            "run",
            "do",
            "work",
            "--route",
            "millrace",
            "--intake",
            "probe",
            "--no-notify-terminal-stages",
        ]
    )

    assert args.route == "millrace"
    assert args.intake == "probe"
    assert args.notify_terminal_stages is False


def test_operator_parser_accepts_intake() -> None:
    args = _parser().parse_args(["operator", "--intake", "idea"])

    assert args.intake == "idea"
    assert args.notify_terminal_stages is True
