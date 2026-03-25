# ABOUTME: Frame-level projection accessor providing rollforward entry point.
# ABOUTME: Creates RollforwardBuilder instances from ActuarialFrame columns.

"""Frame-level projection accessor for rollforward operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio_core.accessors.base import BaseFrameAccessor
from gaspatchio_core.frame.registry import register_accessor
from gaspatchio_core.rollforward._builder import RollforwardBuilder

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame


@register_accessor("projection", kind="frame")
class ProjectionFrameAccessor(BaseFrameAccessor):
    """Frame-level accessor for actuarial projection operations.

    Provides the ``rollforward()`` method to create a ``RollforwardBuilder``
    for non-linear account value projections.

    Accessed via ``.projection`` on an ``ActuarialFrame``, e.g.,
    ``af.projection.rollforward(initial=af.av_init)``.
    """

    def __init__(self, frame: ActuarialFrame) -> None:
        super().__init__(frame)

    def rollforward(
        self,
        *,
        initial: Any = None,  # noqa: ANN401
        track_increments: bool = False,
        **state_initials: Any,  # noqa: ANN401
    ) -> RollforwardBuilder:
        """Create a rollforward builder for account value projection.

        Use ``initial`` for single-state mode (one account value), or pass
        named keyword arguments for multi-state mode (multiple state
        variables).

        Parameters
        ----------
        initial
            Column reference for the single account value. Use this for
            single-state rollforward. Mutually exclusive with
            ``**state_initials``.
        track_increments : bool
            Whether to capture per-step increments for diagnostics.
        **state_initials
            Named state variables for multi-state rollforward. Each key
            is a state name and each value is a column reference for that
            state's initial value.

        Returns
        -------
        RollforwardBuilder
            A new builder instance bound to this frame.

        Raises
        ------
        ValueError
            If both ``initial`` and ``**state_initials`` are provided, or
            if neither is provided.

        Examples
        --------
        Single-state::

            b = af.projection.rollforward(initial=af.av_init)

        Multi-state::

            b = af.projection.rollforward(av=af.av_init, guarantee=af.g_init)
        """
        if initial is not None and state_initials:
            msg = (
                "Provide either 'initial' (single-state) or named keyword "
                "arguments (multi-state), not both."
            )
            raise ValueError(msg)

        if initial is None and not state_initials:
            msg = (
                "Either 'initial' (single-state) or named keyword arguments "
                "(multi-state) must be provided."
            )
            raise ValueError(msg)

        if initial is not None:
            return RollforwardBuilder(
                frame=self._frame,
                initial=initial,
                track_increments=track_increments,
            )

        return RollforwardBuilder(
            frame=self._frame,
            states=state_initials,
            track_increments=track_increments,
        )
