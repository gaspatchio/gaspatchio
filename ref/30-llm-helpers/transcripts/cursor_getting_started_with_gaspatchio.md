# Getting started with gaspatchio
_Exported on 27/03/2026 at 14:07:32 GMT+13 from Cursor (2.6.21)_

---

**User**

"I just installed gaspatchio. What should I do first?"

---

**Cursor**

I'm using the gaspatchio quickstart skill to get you started.

Let's verify the installation first.

You're on **gspio 0.2.0** — installation looks good.

Now, to route you to the right starting point: do you have any data files (policy data, assumption tables, etc.) you want to work with, or are you just exploring the framework?

If exploring, I'll default you to **Level 1 — Hello World**, which is ~60 lines and covers the four core concepts:
1. `ActuarialFrame` — the projection container
2. Column arithmetic — defining cashflow formulas
3. `when/then` — conditional logic (like IF in Excel)
4. `collect` — running the projection

Which fits you best?

> **Which tutorial level do you want to start with?**
> - Level 1 — Hello World (just exploring, basic policy cashflows) ✔
> - Level 2 — Assumptions (I have mortality/lapse tables)
> - Level 3 — Mini VA (variable annuity with account values/guarantees)
> - Level 4 — Lifelib (porting from lifelib or another platform)
> - Level 5 — Scenarios (deterministic stress testing / sensitivity)

Level 1 it is. Let me copy the tutorial and run it.

Now I have a clear picture of the API. The tutorial files aren't shipped with the package — let me write a working Hello World model directly.

The API is working. Now let me write the proper Hello World model:

`accumulate` needs list columns for `multiply` and `add`. I need to build a list column of `v_factor` values per policy, then accumulate. Let me fix the discount factor approach:

It runs. The framework is also warning about a slow `map_elements` — let me fix that with native expressions:

Clean run, no warnings. Your first gaspatchio model is live at `my-first-model/model.py`.

---

Here's what it does and what each output means:

**Model points** — 3 policies with different ages, sum assured, premiums, and payment terms (5yr / 3yr / 2yr).

**Premium cashflows** — a list of 60 monthly values per policy. P001 pays £100/month all 60 months; P002 pays £200/month for 36 months then zeros out.

**Present values** (5% p.a. flat discount rate):
- `pv_premiums` — PV of all premium income
- `pv_benefits` — PV of the death benefit (simplified: full sum assured paid at month 59)
- `net_liability` — the shortfall (benefits exceed premiums, as expected for pure term)

---

The four core concepts you just used:

| Concept | What you did |
|---|---|
| `ActuarialFrame` | Wrapped a dict of policy data + projection timeline |
| Column arithmetic | `annual_premium / 12`, `v ** t` |
| `list_conditional` | Element-wise `when t < term_months → pay, else 0` |
| `collect()` | Materialised the lazy computation into a DataFrame |

**Where to go next:**
- Add mortality rates → use `accumulate` to build a survival curve
- Load real policy data from parquet → `ActuarialFrame(pl.read_parquet("data.parquet"))`
- Assumption tables (age-based mortality/lapse) → that's **Level 2**, use `gspio docs "Table lookup assumptions"`
- Build a full model from scratch → ask me and I'll use the `gaspatchio-model-discovery` skill

