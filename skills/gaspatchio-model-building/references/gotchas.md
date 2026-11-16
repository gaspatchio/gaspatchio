# Gotcha quick reference

These are the top mistakes from real model-building sessions. Each links to the reference file that explains it.

| # | Gotcha | What Goes Wrong | Reference |
|---|--------|----------------|-----------|
| 1 | Arithmetic-masking blends in conditional code | Old workaround for a fixed limitation — `when/then/otherwise` now handles mixed scalar/list branches | [conditionals-and-lists.md](conditionals-and-lists.md) |
| 2 | `until_value=99` | Truncates final year; ~3% BEL gap | [model-phases.md](model-phases.md) |
| 3 | `proj_year` vs `year` confusion | Stress scenarios silently wrong — mass lapse never fires | [timing-and-dates.md](timing-and-dates.md) |
| 4 | Rebuilding `af.month` by hand | `projection.set()` already materialises `month` (elapsed whole months, `n_periods + 1` point-indexed values). Don't derive it from `period_dates()`. A rollforward input needs one value per *period*: pass a per-policy value as it stands, or build the input from `af.projection.year_fractions()` — not from `month` | [model-phases.md](model-phases.md) |
| 5 | `python3` instead of `uv run python3` | `ModuleNotFoundError: No module named 'polars'` | (SKILL.md, Environment section) |
| 6 | `--policy-id` flag | It's a positional arg, not a flag. `--policy-id-column` is a different thing | (SKILL.md, Environment section) |
| 7 | `prospective_value` timing | `end_of_period` = ordinary annuity (Excel type 0), `beginning_of_period` = annuity-due (type 1); BoP is worth more | [timing-and-dates.md](timing-and-dates.md) |
| 8 | `ceil(t/12)` for proj_year | Leap years cause 1-month offset that compounds under stress | [timing-and-dates.md](timing-and-dates.md) |
| 9 | Column name case mismatch | Polars is case-sensitive; always check `df.columns` first | [common-mistakes.md](common-mistakes.md) |
| 10 | Guessing method signatures | Agents get it wrong ~70% of the time — `gspio docs` first | (SKILL.md, MANDATORY: Look Up Before You Write) |
| 11 | `af.month * 0 + CONSTANT` broadcast hack | Confusing — just assign the scalar directly: `af.rate = CONSTANT` | [common-mistakes.md](common-mistakes.md) |
| 12 | `(1 + rate) ** af.month` scalar^list | Now works — `**` operator handles all list/scalar combinations | [common-mistakes.md](common-mistakes.md) |
| 13 | Boolean masking in audit code | `value * (condition)` is a programmer's trick — use `when/then` | [conditionals-and-lists.md](conditionals-and-lists.md) |
| 14 | Writing `(1 + r) ** (1/12) - 1` inline | `finance.to_monthly()` already exists — use it | (SKILL.md) |
| 15 | Writing `months_between` inline | `date.months_between()` already exists — use it | (SKILL.md) |
| 16 | Scalar `until_value` with mixed terms | All policies get max-length lists; wasted memory and compute — use a per-policy column (`until_value="<col>"`) instead |
| 17 | Hand-rolling `(1+r)**(-t/12)` for yield-curve discounting | For a term-structure / EIOPA risk-free rate, use `Curve.discount_factor(af.projection.t_years())` — correct interpolation, flat extrapolation, stress-ready | [curves-and-scheduling.md](curves-and-scheduling.md) |
| 18 | Reaching for `.polars_native()` | The line records as `engine_native`: it runs only on Polars, and so does every calculation that reads it — `af.graph.tiers()` names the line, and `gspio validate --engine jax` names it and every calculation that reads it. Prefer the declared form where one exists: `list.reverse()`, `fill_nan(0.0)`, `norm_cdf()`, `accumulate(reverse=True)`, `(af.x >= lo) & (af.x <= hi)` for `is_between` | [common-mistakes.md](common-mistakes.md) |
| 19 | A line refused at assignment | Kind refusals (a number filled with text, branches of two kinds, a date compared with a number), row guards (a period method on a per-policy column, an unnamed `with_columns`), and a table read inside an engine expression each name the line to write instead | [common-mistakes.md](common-mistakes.md) |
| 20 | `previous_period()` feeding a running product | Its default fill is `0.0`, which zeroes every later period of a `cum_prod()` — pass `fill_value=1.0` | [common-mistakes.md](common-mistakes.md) |
| 21 | Reading `accumulate` one step out | Position `t` is the state *after* step `t`; the opening value is not in the list — shift with `.projection.previous_period(fill_value=initial)` to compare with a column that starts at its opening value | [recursive-patterns.md](recursive-patterns.md) |
| 22 | Building Φ from `erf` or a polynomial | `af.z.norm_cdf()` is the standard normal distribution function, recorded as a core operation; Excel's `NORM.S.DIST(z, TRUE)` is `af.z.excel.norm_s_dist()` | [common-mistakes.md](common-mistakes.md) |
| 23 | `previous_period(fill_value=af.column)` to open each policy's run with its own value | The fill is one value for every policy, so a column is refused. Shift with a number and replace the first period: `when(af.month == 0).then(af.opening_value).otherwise(af.run.projection.previous_period())` | [conditionals-and-lists.md](conditionals-and-lists.md) |
| 24 | `when(...).then(x).otherwise(None)` for a blank | The specification has no core null, so a `None` branch records the line as engine_native: it runs only on Polars and `gspio validate --engine jax` refuses the model. It warns at the line. If blank means zero, write `.otherwise(0.0)`; otherwise use a sentinel value you test with `==` | [conditionals-and-lists.md](conditionals-and-lists.md) |

Full list with code examples: [common-mistakes.md](common-mistakes.md)
