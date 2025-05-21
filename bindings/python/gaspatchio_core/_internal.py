"""Stub module used when the compiled extension is unavailable."""

__file__ = __file__

class PyTableRegistry:
    """Placeholder for the Rust-backed table registry."""

    def register_table(self, *args, **kwargs):
        raise RuntimeError(
            "PyTableRegistry is not available in this environment."
        )
