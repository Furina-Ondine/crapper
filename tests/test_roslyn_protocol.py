"""Include the standalone compiler protocol checks in the normal CI suite."""

from pathlib import Path
import subprocess
import sys

from crapper import roslyn


def test_compiler_protocol_against_the_selected_sdk():
    sdk = roslyn._sdk(str(Path.cwd()))
    binary = roslyn._build(sdk, roslyn._fingerprint(sdk))
    result = subprocess.run(
        [sys.executable, str(roslyn._HOST / "tests/protocol_test.py"), str(binary)],
        capture_output=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
