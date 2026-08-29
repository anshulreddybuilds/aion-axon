import os
import subprocess
import sys
from pathlib import Path


def test_approval_resume_end_to_end():
    project_root = Path(__file__).resolve().parents[1]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    result = subprocess.run(
        [sys.executable, "scripts/probe_approval_resume.py"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Approval-resume flow failed:\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    assert "END-TO-END APPROVAL RESUME: PASS" in result.stdout
