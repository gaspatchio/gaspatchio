# Two-Stage Aggregate Patterns

Models that project per-entity, then aggregate to a fund/plan/portfolio level for financial reporting.

## When This Applies

- Fund NAV models (per-investor → fund P&L, balance sheet, unit price)
- DB pension funding (per-member → plan-level contribution rate)
- IFRS 17 portfolio (per-cohort → group-level CSM, P&L)
- Reinsurance treaty (per-cedant → treaty aggregate)

The key signal: you need per-entity detail AND portfolio-level financial statements.

---

## The Pattern: Four Phases

Standard gaspatchio models have 3 phases. Aggregate models add a 4th:

| Phase | What Happens | Tools |
|---|---|---|
| **Phase 1** | Setup: load data, join parameters, create AF | `Table()`, `.collect()`, `.join()` |
| **Phase 2** | Timeline: `create_projection_timeline()` | `.date.create_projection_timeline()` |
| **Phase 3** | Per-entity calculations using AF | Column ops, `accumulate`, `when/then`, `Table.lookup` |
| **Phase 4** | Aggregate + fund-level outputs | `.collect()` → `group_by().agg()` → fund financials |

**Phase 4 is where `.collect()` is OK again.** The per-entity projection is complete; now you're aggregating results.

---

## Phase 3 → Phase 4 Transition

```python
# End of Phase 3: per-entity results are list columns in AF
af.equity = af.income * (1 - GST_RATE)
af.interest = af.income * (1 - GST_RATE) * af.gearing - af.equity
af.mgmt_fee = af.effective_fee * af.income

# Phase 4: collect and aggregate
result = af.collect()

# Aggregate per-entity results to fund level by period
fund = result.explode([
    "equity", "interest", "mgmt_fee", "month"
]).group_by("month").agg([
    pl.col("equity").sum().alias("total_equity"),
    pl.col("interest").sum().alias("total_interest"),
    pl.col("mgmt_fee").sum().alias("total_mgmt_fee"),
])
```

### Why `explode` + `group_by`?

After Phase 3, each entity's results are list columns (one list per entity, one element per period). To aggregate across entities for the same period:

1. `explode` unrolls lists into rows (entity × period)
2. `group_by("period")` groups all entities for the same period
3. `.agg()` sums/averages across entities

---

## Fund-Level Financial Statements (Phase 4)

Fund-level P&L and balance sheets often have cross-line dependencies:

- Expenses depend on prior period's total equity
- Cash flow depends on net income + non-cash adjustments
- Balance sheet items accumulate over time

These CAN be handled with gaspatchio methods — the same tools used in Phase 3 work here too:

| Pattern | Method |
|---------|--------|
| "Prior period's value" | `previous_period(fill_value=0.0)` or Polars `.shift(1).fill_null(0.0)` |
| "Running balance" | `accumulate(initial=X, multiply=1.0, add=flow)` |
| "Cumulative total" | `.list.cumsum()` or Polars `.cum_sum()` |
| "Circular dependency" (expenses depend on equity, equity depends on expenses) | Rearrange into `accumulate()` form — see example below |

**Phase 3 methods work in Phase 4 too.** `previous_period()`, `accumulate()`, `ceil()`, `round()`, and all other AF column methods work on scalar columns (across rows), not just list columns (within lists). You don't need to drop to raw Polars for fund-level calculations.

### Preferred: Vectorised fund financials

```python
# Fund-level data from Phase 4 aggregation (one row per period)
# Revenue (no dependency on prior periods)
fund = fund.with_columns(
    (pl.col("interest") + pl.col("gains") + pl.col("interest_on_cash"))
    .alias("total_revenue"),
)

# Expenses depend on prior period's total equity — use shift(1)
fund = fund.with_columns(
    (-MGMT_FEE_RATE * pl.col("total_equity").shift(1).fill_null(0.0) / 12)
    .alias("mgmt_expense"),
    (-EXPENSE_RATE * pl.col("total_equity").shift(1).fill_null(0.0) / 12)
    .alias("expense_recovery"),
)

# BUT: total_equity itself depends on expenses (circular).
# Break the circularity by solving the linear recurrence:
#   equity[t] = equity[t-1] * (1 + fee_factor) + independent_flows[t]
# where fee_factor = -total_fee_rate * (1 - tax_rate) / 12
#
# Use a helper single-row AF with accumulate:
equity_mult = 1.0 + TOTAL_FEE_RATE * (TAX_RATE - 1.0) / 12
indep_flows = (contributions + revenue + taxes).to_list()

helper_af = ActuarialFrame({
    "mult": [[equity_mult] * n_periods],
    "add": [indep_flows],
})
helper_af.equity = helper_af.mult.projection.accumulate(
    initial=0.0,
    multiply=helper_af.mult,
    add=helper_af.add,
)
equity_values = helper_af.collect()["equity"][0].to_list()
fund = fund.with_columns(pl.Series("total_equity", equity_values))

# Now expenses can be derived from the solved equity
fund = fund.with_columns(
    (-MGMT_FEE_RATE * pl.col("total_equity").shift(1).fill_null(0.0) / 12)
    .alias("mgmt_expense"),
)

# Cash balance: running sum
fund = fund.with_columns(
    pl.col("net_cash_flow").cum_sum().alias("cash_balance"),
)

# Balance sheet: cumulative asset/liability totals
fund = fund.with_columns(
    pl.col("home_equity").cum_sum().alias("cum_home_equity_asset"),
    pl.col("unrealised_gain").cum_sum().alias("cum_gain_asset"),
    (-pl.col("deferred_tax")).cum_sum().alias("cum_deferred_tax_liability"),
)

# NAV and unit price
fund = fund.with_columns(
    (pl.col("total_assets") - pl.col("total_liabilities")).alias("nav"),
    (pl.col("total_equity") / UNITS).alias("unit_price"),
)
```

### When a Python loop IS justified

A `for` loop over periods is acceptable ONLY when there is a multi-variable circular dependency that cannot be rearranged into `accumulate()` form — for example, if expense rates themselves change based on a threshold of the prior period's NAV (state-machine logic). In that case:

1. State explicitly WHY it can't be vectorised
2. Limit the loop to the fund-level data only (never loop over entities)
3. Use `af.collect().to_dicts()` and build the result as a list of dicts

---

## When to Use Polars Directly in Phase 4

Some fund-level calculations are genuinely one-off and don't benefit from AF:

- **Ratio calculations**: NAV per unit, expense ratios — simple division after aggregation
- **Cross-entity statistics**: max/min/percentile across entities — Polars `describe()` or quantile
- **Pivot tables**: reshape entity × period data for reporting

For these, staying in Polars after the Phase 4 collect is fine:

```python
fund = fund.with_columns([
    (pl.col("total_assets") - pl.col("total_liabilities")).alias("nav"),
])
fund = fund.with_columns([
    (pl.col("nav") / UNITS_OUTSTANDING).alias("unit_price"),
])
```

The rule: use AF when you need its methods (accumulate, previous_period, Table.lookup). Use raw Polars when you're doing simple column arithmetic on the aggregated result.

---

## Anti-Pattern: Python Loops for Per-Entity Calculations

```python
# WRONG — defeats gaspatchio entirely
for inv in mp.iter_rows(named=True):
    for month in months:
        equity = round(inv["income"] * (1 - GST), 2)
        ...
    results.append(...)

# RIGHT — vectorised per-entity in AF, aggregate in Polars
af.equity = af.income * (1 - GST_RATE)
...
result = af.collect()
fund = result.explode([...]).group_by("month").agg([...])
```

Even with 9 entities, the AF approach is preferable because:
1. It's auditable — each formula is one line
2. It scales — switch from 9 to 9,000 entities with no code change
3. It follows the standard pattern — anyone who knows gaspatchio can read it
