"""Every colour pair the design uses meets WCAG 2.2 AA contrast."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_contrast.py"


def test_design_tokens_meet_the_contrast_minimums(capsys):
    spec = importlib.util.spec_from_file_location("check_contrast", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0, capsys.readouterr().out
