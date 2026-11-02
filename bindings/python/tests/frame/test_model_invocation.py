# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Model invocation follows the frame's choice and never retries a model body."""

from __future__ import annotations

from typing import Literal

import pytest

from gaspatchio import ActuarialFrame, run_model, set_default_mode


@pytest.mark.parametrize("mode", ["debug", "optimize"])
@pytest.mark.parametrize("successor", [False, True])
def test_one_invocation_preserves_the_returned_frame_and_explicit_mode(
    mode: Literal["debug", "optimize"],
    *,
    successor: bool,
) -> None:
    set_default_mode("optimize" if mode == "debug" else "debug")
    af = ActuarialFrame({"amount": [2.0]}, mode=mode)
    calls: list[ActuarialFrame] = []

    def model(frame: ActuarialFrame) -> ActuarialFrame | None:
        calls.append(frame)
        frame.reserve = frame.amount * 2
        return ActuarialFrame({"reserve": [4.0]}, mode=mode) if successor else None

    finished = run_model(model, af)
    assert calls == [af]
    assert (finished is af) is not successor
    assert finished._traced_run is (mode == "debug")  # noqa: SLF001 -- diagnostic choice
    assert finished.graph.last_run is None  # Building did not collect.
    assert finished.collect()["reserve"].to_list() == [4.0]


@pytest.mark.parametrize("mode", ["debug", "optimize"])
def test_model_typeerror_propagates_once_without_stdout(
    mode: Literal["debug", "optimize"],
    capsys: pytest.CaptureFixture[str],
) -> None:
    af = ActuarialFrame({"amount": [2.0]}, mode=mode)
    calls = 0
    failure = TypeError("inside the model body")

    def model(_frame: ActuarialFrame) -> ActuarialFrame:
        nonlocal calls
        calls += 1
        raise failure

    with pytest.raises(TypeError, match="inside the model body") as caught:
        run_model(model, af)
    assert caught.value is failure
    assert calls == 1
    assert capsys.readouterr().out == ""
