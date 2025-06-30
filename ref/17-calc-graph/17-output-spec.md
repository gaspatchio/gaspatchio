### Spec — Line-by-Line *Trace* (“Proof”) blocks for each computed variable

*(deliverable: JSON-serialisable data model + worked examples an actuary can read at a glance)*

---

#### 1  Purpose

Give actuaries a clear, auditable *proof* of how every derived column is produced, by unfolding each formula one operation at a time and showing the numeric substitutions coming from its dependencies.

#### 2  Scope

Applies to any `type: "computed"` node in the existing calculation-graph JSON (e.g. the file `year7_full.json`) that already carries `formula`, `dependencies`, `value_sample`, etc. Input nodes remain unchanged.

#### 3  Schema extension

Add a **`trace`** array under `data` for every computed node.

```ts
trace: TraceStep[]

interface TraceStep {
  step:       number          // 1-based sequence index
  expr:       string          // human-readable expression at this step
  values?:    Record<string, number|string|null>  // optional map of “symbol → value” inserted at this step
  result?:    number|string|null                  // final numeric/string value once fully resolved
  comment?:   string           // optional human note (“clip lower bound to 0”, etc.)
}
```

Rules

* **Step 1** is always the raw algebraic form, using dependency names.
* Each subsequent step performs **exactly one** evaluation (parentheses, arithmetic op, function call, clip, lookup, etc.).
* When a dependency’s value is first substituted, include the `values` map for transparency.
* The step that leaves a single literal must include `result`.
* Omit `values` or `result` when not meaningful (keeps payload small).

#### 4  Worked examples *(excerpt only – the rest of each node stays untouched)*

##### 4.1  Node `issue_age`

```json
{
  "id": "issue_age",
  "type": "computed",
  "label": "issue_age = Policyholder issue age + term_offset",
  "data": {
    "formula": "[(col(\"Policyholder issue age\")) + (col(\"term_offset\"))]",
    "dependencies": ["Policyholder issue age", "term_offset"],
    "trace": [
      { "step": 1, "expr": "Policyholder issue age + term_offset" },
      {
        "step": 2,
        "expr": "38 + 0",
        "values": { "Policyholder issue age": 38, "term_offset": 0 }
      },
      { "step": 3, "expr": "38", "result": 38 }
    ],
    "value_sample": 38.0
  }
}
```

Sample numbers taken from the existing JSON (`value_sample` fields) .

##### 4.2  Node `age_mort_lookup`

```json
{
  "id": "age_mort_lookup",
  "type": "computed",
  "label": "age_mort_lookup = issue_age + clip(year - 26, 0)",
  "data": {
    "formula": "[(col(\"issue_age\")) + ([(col(\"year\")) - (dyn int: 26)].eval())]",
    "dependencies": ["issue_age", "year"],
    "trace": [
      { "step": 1, "expr": "issue_age + max(year - 26, 0)" },
      {
        "step": 2,
        "expr": "38 + max(3 - 26, 0)",
        "values": { "issue_age": 38, "year": 3 }
      },
      { "step": 3, "expr": "38 + 0", "comment": "clip result non-negative" },
      { "step": 4, "expr": "38", "result": 38 }
    ],
    "value_sample": 38.0
  }
}
```

Numbers again come from `value_sample` entries for `issue_age` (38.0) and `year` (3.0) .

##### 4.3  Node `CSO table`

```json

{
  "id": "monthly_CSO_table",
  "type": "computed",
  "label": "monthly_CSO_table = CSO table*(13-month)/12 + CSO table next year*(month-1)/12",
  "data": {
    "formula": "[[(col(\"CSO table\")) * (13 - col(\"month\")) / 12] + \
                [[col(\"CSO table next year\")) * (col(\"month\") - 1) / 12]]",
    "dependencies": ["CSO table","CSO table next year","month"],
    👉 "trace": [
      { "step": 1,
        "expr": "CSO table*(13 - month)/12 + CSO table next year*(month - 1)/12" },
      { "step": 2,
        "expr": "0.00095*(13 - 8) / 12 + 0.00111*(8 - 1) / 12",
        "values": { "CSO table": 0.00095, "CSO table next year": 0.00111, "month": 8 } },
      { "step": 3,
        "expr": "0.00095*5 / 12 + 0.00111*7 / 12" },
      { "step": 4,
        "expr": "0.00475 / 12 + 0.00777 / 12" },
      { "step": 5,
        "expr": "0.000395833 + 0.0006475" },
      { "step": 6,
        "expr": "0.001043333",
        "result": 0.001043 }
    ],
    "value_sample": 0.001043,
    "dtype": "list"
  }
}
```

##### 4.4  Node `ann`

```json
{
  "id": "annual_prob_inforce",
  "type": "computed",
  "label": "annual_prob_inforce = (1-mortality_rates)*(1-surrender_charge)",
  "data": {
    "formula": "[(1 - col(\"mortality_rates\")) * (1 - col(\"surrender_charge\"))]",
    "dependencies": ["mortality_rates","surrender_charge"],
    👉 "trace": [
      { "step": 1,
        "expr": "(1 - mortality_rates) * (1 - surrender_charge)" },
      { "step": 2,
        "expr": "(1 - 0.000087) * (1 - 0.002535)",
        "values": { "mortality_rates": 0.000087, "surrender_charge": 0.002535 } },
      { "step": 3,
        "expr": "0.999913 * 0.997465" },
      { "step": 4,
        "expr": "0.997378",
        "result": 0.997378 }
    ],
    "value_sample": 0.997378,
    "dtype": "list"
  }
}

```




#### 5  Developer tasks

1. **Generator**

   * When a computed column finishes evaluation for a row, build the `trace` array as described and attach it to the node before serialising the graph.
   * Optimise for the *first* row only (or small sample) to keep file size reasonable; downstream UIs will label it “sample trace”.

2. **Validation**

   * Unit-test that each `trace` ends with `result == value_sample` for consistency.

3. **Front-end rendering (later)**

   * Display each step as an expandable list inside the node card (React Flow / SvelteFlow).
   * Provide a toggle to hide intermediate steps for power users.

---

With this spec the dev team can retrofit *trace* blocks onto the existing graph engine and give actuaries an instant, line-by-line proof of every calculation.
