# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import polars as pl

from gaspatchio import ActuarialFrame

data = {
    "policy_id": ["A1", "A2"],
    "claim_notes": [
        ["NOTE: Initial review", "Payment authorised"],
        [None, "NOTE: Follow up required"],
    ],
}
af = ActuarialFrame(data)

af.clean_notes = af.claim_notes.polars_native().list.eval(
    pl.element().str.replace("NOTE: ", "", literal=True, n=1)
)

print(af.collect())
