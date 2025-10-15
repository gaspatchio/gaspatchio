import os
import shutil
import subprocess
import textwrap


def _has_pyright() -> bool:
    exe = shutil.which("pyright")
    return exe is not None


def test_pyright_sees_columnproxy_on_attribute(tmp_path):
    if not _has_pyright():
        # Skip gracefully if pyright not installed in env
        return

    code = textwrap.dedent(
        """
        from gaspatchio_core import ActuarialFrame
        
        af = ActuarialFrame({"age": [1, 2, 3]})
        _x = af.age.ceil()  # should be valid if __getattr__ -> ColumnProxy
        """
    )
    sample = tmp_path / "sample.py"
    sample.write_text(code)

    env = os.environ.copy()
    # prefer project's pyright if available via uv/pdm/poetry
    result = subprocess.run(
        ["pyright", str(sample)], check=False, capture_output=True, text=True, env=env
    )

    # pyright exits nonzero when errors found
    assert result.returncode == 0, (
        f"pyright failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
