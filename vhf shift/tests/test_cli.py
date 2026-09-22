from meteor_lease.cli import build_parser


def test_parser_defaults_to_stub_and_dry_run():
    args = build_parser().parse_args(["pass", "--yes"])
    assert args.decoder == "stub"
    assert args.stub is False
    assert args.commit is False
    assert args.yes is True
