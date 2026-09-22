from ism_scanner.procs import Proc, ancestors, rtl_433_owners, serve_processes

LISTING = [
    Proc(1, 0, "/sbin/launchd"),
    Proc(100, 1, "/bin/zsh"),
    # The classic footgun: a shell whose command line *mentions* ism-scan serve.
    Proc(200, 100, '/bin/zsh -c pkill -f "ism-scan serve"; uv run ism-scan serve --port 4330'),
    Proc(201, 200, "uv run ism-scan serve --port 4330"),
    Proc(
        202,
        201,
        "/Users/x/Hardware and Telemetry/433 scanner/.venv/bin/python "
        "/Users/x/Hardware and Telemetry/433 scanner/.venv/bin/ism-scan serve --port 4330",
    ),
    Proc(203, 202, "rtl_433 -f 433.92M -M time:iso:usec:utc -F json -d 0"),
    Proc(300, 100, "/opt/homebrew/bin/rtl_433 -f 315M"),
    Proc(400, 100, "grep ism-scan serve"),
]


def test_serve_processes_skip_shells_and_greps_and_report_roots():
    found = {proc.pid for proc in serve_processes(LISTING, exclude=set())}
    assert found == {201}  # the uv root; its python child (202) rides along


def test_serve_processes_find_bare_python_launcher_with_spaces_in_path():
    listing = [Proc(1, 0, "/sbin/launchd"), LISTING[4]]
    assert {proc.pid for proc in serve_processes(listing, exclude=set())} == {202}


def test_serve_processes_skip_own_ancestry(monkeypatch):
    monkeypatch.setattr("os.getpid", lambda: 202)
    found = {proc.pid for proc in serve_processes(LISTING)}
    assert found == set()


def test_rtl_433_owners_only_binaries():
    found = {proc.pid for proc in rtl_433_owners(LISTING)}
    assert found == {203, 300}


def test_ancestors_walks_to_launchd():
    assert ancestors(203, LISTING) == {203, 202, 201, 200, 100}
