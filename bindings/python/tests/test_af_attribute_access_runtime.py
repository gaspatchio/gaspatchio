# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import polars as pl

from gaspatchio_core import ActuarialFrame


def test_attribute_access_returns_column_proxy_and_has_methods():
    af = ActuarialFrame({"age": [30, 40, 50], "premium": [100.0, 200.5, 300.2]})

    # attribute access returns a proxy that supports standard ops
    expr = af.age.ceil()

    # Ensure it composes and materializes
    out = af.select(expr.alias("age_up")).collect()
    assert isinstance(out, pl.DataFrame)
    assert out.shape == (3, 1)
    assert out["age_up"].to_list() == [30.0, 40.0, 50.0]
