# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from gaspatchio import ActuarialFrame

data = {
    "policy_id": ["A1", "A2"],
    "claim_notes": [
        ["NOTE: Initial review", "Payment authorised"],
        [None, "NOTE: Follow up required"],
    ],
}
af = ActuarialFrame(data)

af.clean_notes = af.claim_notes.str.replace("NOTE: ", "", literal=True, n=1)

print(af.collect())
