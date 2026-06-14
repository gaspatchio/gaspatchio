# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import Literal

import polars as pl

from gaspatchio_core.assumptions import Table

type AgeBasis = Literal["age_last_birthday", "age_nearest_birthday"]
type Structure = Literal["aggregate", "select_ultimate", "joint"]

class MortalityTable:
    table: Table
    age_basis: AgeBasis
    structure: Structure
    select_period: int | None

    def __init__(
        self,
        table: Table,
        age_basis: AgeBasis,
        structure: Structure,
        select_period: int | None = ...,
    ) -> None: ...
    def __post_init__(self) -> None: ...
    def at(
        self,
        *,
        age: pl.Expr | None = ...,
        age_1: pl.Expr | None = ...,
        age_2: pl.Expr | None = ...,
        duration: pl.Expr | None = ...,
        age_basis: AgeBasis | None = ...,
        **other: pl.Expr,
    ) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, object]: ...
    def source_sha(self) -> str: ...

__all__ = ["AgeBasis", "MortalityTable", "Structure"]
