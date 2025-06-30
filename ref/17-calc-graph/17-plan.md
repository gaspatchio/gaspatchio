Thanks! I’ll create a comprehensive design document that synthesizes GH issues #49 and #50 with the project’s source files, DSL architecture, and principles. I’ll also analyze how frameworks like PyTorch, Dask, and Excel handle similar challenges around computation graph introspection and debugging.

The design doc will cover:

* Goals and UX requirements (e.g. tracing, debugging, Excel-style explainability)
* Core design proposals (structure of computation graphs, node metadata, graph emission format)
* Implementation options (tradeoffs for static vs dynamic capture, proxy vs AST, integration with ActuarialFrame)
* Appendix: relevant visualization integration format recommendations (e.g. React Flow-ready graph schema).

I’ll return shortly with the proposed design document.


# Design: Computation Graph Capture for Traceability & Debugging in Gaspatchio

## Introduction

Gaspatchio models must be as transparent and auditable as Excel spreadsheets. Actuaries need to trace any output value back through the formula steps that produced it, similar to Excel’s **formula auditing** (Trace Precedents/Dependents) which graphically shows how cells feed into one another. GitHub issues #49 and #50 highlight two key enhancements toward this goal: (1) a robust mechanism to capture the **computation graph** of all column calculations in an ActuarialFrame, and (2) the ability to inspect and visualize that graph with *Excel-like* clarity (showing formulas *and actual values* for each dependency). The following design addresses both issues by defining how Gaspatchio can record every column’s derivation (for traceability and explainability), and emit the graph in a shareable format. We also compare approaches from other frameworks (PyTorch, Dask, Excel) to inform our solution, and evaluate implementation options (AST vs proxies vs tracing) in the context of Gaspatchio’s dual execution modes. Throughout, we connect decisions to Gaspatchio’s core principles of **explainability**, **debuggability**, and **production-readiness**.

## 1. Capturing the ActuarialFrame Computation Graph

**Goal:** Every time a column is computed in the ActuarialFrame DSL, record a node in a directed acyclic graph (DAG) representing that computation, with edges to all input columns, constants, or plugin outputs it depends on. This “computation graph” should comprehensively represent how final outputs are derived from inputs, enabling complete traceability.

**Mechanism:** Gaspatchio will leverage its existing tracing hooks in `ActuarialFrame` to capture column operations at runtime. Currently, `ActuarialFrame` wraps a Polars DataFrame and **appends each operation to an internal graph list** when tracing is active. We will extend this such that when a user writes, for example, `af["net_premium"] = af["gross_premium"] - af["expenses"]`, the framework creates a `TracedOperation` node for `"net_premium"` with a formula referencing `gross_premium` and `expenses`. Each node stores the *alias* (column name) and the Polars expression used to compute it. Critically, we also populate a **dependency list** on the node (e.g. `dependencies = ["gross_premium", "expenses"]`) so that later we can traverse what inputs fed into this column. Any **constant literals** in the expression (e.g. a `+ 1000` adjustment) will be captured as well – they can either be represented as special “constant” nodes or simply noted in the formula string.

To implement this, we augment the `__setitem__` override and related tracing logic in ActuarialFrame:

* **During tracing** (development/debug mode), each `af["col"] = expr` call will *not only execute* the assignment but also create a `TracedOperation` entry in `af._computation_graph`. This entry includes the Polars `expr` (for evaluation) and metadata (for traceability). The `TracedOperation` object will replace the simple tuple currently used, allowing richer data capture. Internally, `__setitem__` can call a helper (e.g. `append_operation_to_graph`) to construct the node and gather metadata. As a result, *every column assignment is recorded* in order, forming a complete list of operations.

* **Dependency Extraction:** We must determine which prior columns an expression depends on. For simple cases using the DSL, this is implicit in the Polars expression (e.g. `pl.col("gross_premium")`). We can **parse the expression AST or string** to extract column names used. Another approach is to build the dependency list at the time of graph capture: since our DSL uses `ColumnProxy` and `ExpressionProxy` objects, we can tag each `ExpressionProxy` with the column names it wraps. For instance, if `expr = af["A"] + af["B"]`, our proxies know it involves “A” and “B”. We will implement an `extract_dependencies(expr) -> List[str]` utility that inspects a Polars `Expr` or our proxy to return all column references. Plugin functions should likewise reveal their column args (e.g. a mortality table lookup might depend on `age` and `sex` columns). Capturing these dependencies ensures each node can point to its parent nodes in the graph.

* **Plugin & Lookup Operations:** When plugin functions (e.g. `fill_series`, `assumption_lookup`) are used, the resulting column’s node should note that it was produced by a plugin, and list the input columns provided to that plugin. For example, `af["mortality_rate"] = assumption_lookup(af["age"], table="mortality")` would yield a node “mortality\_rate” depending on `age` (and perhaps implicitly on the registered table “mortality”). We will treat plugin outputs as regular computed columns in the graph but include metadata about the plugin name and parameters used. This could be as simple as a label or flag in the node’s metadata (e.g. `origin="plugin:assumption_lookup"`) to aid explainability.

* **Intermediate Variables (Issue #49 Integration):** With the new variable-based syntax (issue #49), users can write `issue_age = policyholder_issue_age + term_offset` instead of `af["issue_age"] = ...`. In such cases, `issue_age` is a Python variable (an `ExpressionProxy`), not immediately a stored column. If a subsequent line uses `issue_age` (e.g. `af["age"] = issue_age + year - 1`), the final assignment will produce a node for “age” with dependencies including “policyholder\_issue\_age” and “term\_offset” (since `issue_age` encapsulates that expression). **However, to preserve the intuitive step-by-step trace**, we may also capture a node for the intermediate `issue_age`. One approach is to treat any assignment to a `ColumnProxy` variable as a *virtual graph node*. We could achieve this by a lightweight static analysis of the model function: e.g., detect `X = ...` where the right-hand side is an ExpressionProxy involving columns, and record a node “X” in the graph (marked as not materialized to the DataFrame). Alternatively, we encourage users who want a specific intermediate trace step to assign it to the frame (making it an actual column). For the design, we assume we can capture intermediate named expressions either via static code parsing or by instrumenting the ActuarialFrame’s context. This ensures the graph can show “issue\_age = policyholder\_issue\_age + term\_offset” as its own node feeding into “age”. It aligns with Excel’s style of breaking complex formulas into helper cells for clarity – here our *computation graph* can include non-output helper nodes corresponding to those variables.

**Dual Execution Mode Considerations:** Gaspatchio runs in two modes – **debug (step-by-step)** and **optimize (batched)**. The graph capture must function in both:

* In **Debug mode**, every column operation executes immediately (e.g. adding a new Polars column and computing it), and we capture the operation at that moment. This yields an *ordered log* of computations which naturally forms the graph. Since debug mode prioritizes transparency, we accept the minor overhead of building the graph on the fly. (In fact, Gaspatchio’s design already appends each operation to `_computation_graph` in debug mode when `_tracing` is enabled.) The result DataFrame is built stepwise, but we retain all the dependency links in the graph.

* In **Optimize mode**, the user’s code is captured but not executed immediately; instead, we batch all operations into a single optimized Polars query for performance. We will adapt the tracing decorator so that in optimize mode it *records operations without applying them* until the end. The `ActuarialFrame.trace(func)` wrapper presently does this: it collects operations in a temporary list and applies them in bulk after `func` returns. We will still populate the graph with each operation (just as in debug mode), but we must be careful: since multiple operations might be fused by Polars, the actual execution might not produce intermediate results one-by-one. **For the sake of traceability, the graph will reflect the *logical* sequence of calculations as written**, not the fused physical execution. For example, if a model does `af["a"]=...; af["b"]=f(a); af["c"]=g(a,b)`, our graph has nodes A -> B -> C, even if Polars internally optimized away the intermediate A. This logical graph is what we expose for explainability, preserving each step. (We might note in metadata if an intermediate was optimized out, but it remains in the trace for clarity.)

* **Performance Impact:** Capturing the graph should be as lightweight as possible, especially when disabled. We will use a flag (like `af._tracing` or a config toggle) to turn on graph capture. If tracing is off (e.g. in pure production runs where no trace is needed), the append function returns immediately, incurring virtually no overhead. This ensures **no performance penalty in production** unless explicitly requested. In tracing-enabled runs, the overhead includes collecting metadata (source line introspection, etc.) for each operation. Tests indicate capturing 100 operations with metadata is on the order of under 2 seconds, which is acceptable for debug usage. We will further optimize metadata gathering (caching file/line lookup for repeated calls).

By systematically recording the computation graph, Gaspatchio moves closer to Excel’s transparency: *every derived column knows exactly what it was derived from*. Next, we leverage this graph for Excel-like debugging and introspection.

## 2. Excel-Style Debugging: Tracing Values Through the Graph

A core deliverable is an **Excel-like “trace precedents” experience** for actuaries. Given a particular output value (e.g. a cell in the result table – identified by column and perhaps row/time index), the system should reveal *how* that value was computed by following the chain of dependencies through the graph. This is analogous to Excel’s **Evaluate Formula** tool, which shows a stepwise substitution of references with values. Our design enables two levels of traceability:

* **Graphical Trace (Structural):** Using the dependency graph, an actuary can navigate upstream from any column to its inputs. For example, selecting the column `net_premium` would show that it depends on `gross_premium` and `expenses`, which might further depend on other inputs. Similar to Excel’s tracer arrows, we can highlight these relationships (more on visualization in Section 4). The graph structure alone answers **“Which inputs influence this value?”**.

* **Value Trace (Formula Audit):** More powerfully, we can show the actual formula and intermediate values that led to a specific number. For instance, if Policy 123’s `net_premium` at time 0 is \$500, the trace might display something like:

  ```
  net_premium = gross_premium – expenses 
              = 1200 – 700 
              = 500
  ```

  This mirrors Excel’s formula audit where you see both the formula and the substituted values. Our design will produce such an output by recursively evaluating the dependencies of the selected cell.

**Implementation:** We introduce a `CalculationTracer` utility (as suggested in issue #50) that, given the captured computation graph and the final computed DataFrame, can answer “how was X (at row i, time t) calculated?”. The process is:

1. **Capture Actual Values:** After model execution, we enrich each graph node with the actual computed results. In debug mode, columns might have been computed eagerly; in optimize mode, we get the final DataFrame upon `collect()`. Either way, we will map back results to the graph. For each `TracedOperation` node, if its alias (column name) exists in the result DataFrame, we attach either the entire series of values or a representative sample. For example, we might store `node.values = [v0, v1, ...]` for scalar columns (or a dictionary for vector columns keyed by time index). To avoid memory blow-up, we can store only a few sample values (e.g. first few and last) and summary stats. In the proposal, they add `sample_values` and `value_shape` for this purpose. Our design adopts **Option A: Post-Execution Value Mapping**, which was recommended in the issue. That is, we first run the model normally (in whichever mode), then iterate over the graph and populate each node’s values from the result. This approach keeps runtime overhead low (no need to store intermediate values during computation) and only slightly delays the presentation of trace info until after results are known. (Option B, tracking every value live, was deemed too memory-intensive.)

2. **Tracing a Specific Cell:** The `CalculationTracer.trace_calculation(column_name, row=i, time=t)` will perform a **depth-first search** or recursion over the graph starting from the target node. For each dependency, it will similarly fetch the value for the same `(row, time)` and build the formula string. For example, to trace `mortality_rates` for policy 1 at time 0, it finds that `mortality_rates = 1 - (1 - monthly_CSO_table) ** (1/12)`. It then looks up `monthly_CSO_table` for policy 1 at time 0 (say 0.000963) and substitutes that in, showing intermediate arithmetic: `1 - (1 - 0.000963) ** 0.08333 = 0.00008`. It continues to trace `monthly_CSO_table` if needed, which might be defined as `= CSO_table * ... + CSO_table_next_year * ...`, and replaces those with their values (from policy 1). Ultimately, this produces a **narrative, stepwise explanation** of the calculation from base inputs (like `CSO_table` value, `month` value, etc.) to the final result. Essentially, we are generating a **tree of formula expansions** rooted at the target cell.

3. **Excel-Like Formatting:** To make the output familiar, we will format each step similar to Excel’s formula bar and auditing reports. The snippet in issue #50 shows a good format: first line “Formula: mortality\_rates = 1 - (1 - monthly\_CSO\_table) \*\* (1/12)” and next line “Values:  mortality\_rates = 1 - (1 - 0.000963) \*\* 0.08333 = 0.00008”. We will implement a formatter that takes a `TracedOperation` and a specific index (row/time) and returns a multi-line string showing the formula with actual values inserted and the computed result. For readability, we might break long formulas into multiple lines aligning the `=` signs as the example does. Each dependency that itself is a computed column will be traced in a similar fashion below, possibly indented or listed under a “Dependencies traced:” section. This way, actuaries can see not only the direct formula for the value, but also how each input in that formula was derived (drilling down as needed).

4. **Vector Columns:** Actuarial models often have vector outputs (e.g. a 480-month projection in one cell). Our trace tool will support specifying a **time index** (or multiple) for such vectors. For instance, `trace.show_vector_evolution("inforce_policies", periods=[0,12,24,60])` might output the value of `inforce_policies` at several time points with the formula context for each. Because a vector may be computed by an accumulation (as in a cumulative product), showing a few key points helps understanding the trajectory. We’ll implement this by simply taking the stored vector and applying the trace at each requested index.

5. **Comparisons and Exports:** The design will also foresee exporting these traces for documentation or debugging outside the interactive session. We plan methods to export the full calculation trace to Excel (possibly generating a worksheet where formulas are written out with values, mimicking the model), to HTML (for a static interactive report), or to Markdown for embedding in docs. These are ancillary features, but our graph data structure will make them straightforward: it’s essentially walking the graph and printing steps, which can be formatted for various mediums. Notably, an **Excel export** could create a sheet where each formula is placed in a cell and precedent arrows could be used, but that is optional future work.

The result of this Excel-style debugging support is a level of **explainability** far above black-box code. An actuary can pick any result and *literally see how it was calculated*, step by step, much like they could in their trusty spreadsheet. This fulfills the principle of making Gaspatchio “feel like you’re writing a spreadsheet, but with the power of a programming language”. It builds trust and eases model validation, since one can compare Gaspatchio’s trace with an equivalent Excel model value-by-value.

## 3. Emitting the Graph for Visualization

Capturing the graph and tracing values is useful in code or logs, but often we’ll want to **visualize** the dependency graph for an entire model. This could be for documentation, for an interactive UI in a web app, or to discuss model structure with stakeholders. The design calls for outputting the computation graph in a format compatible with modern graph visualization tools (like React Flow in a React app). We emphasize that *building the front-end UI is out of scope* – our task is to provide the data and endpoints necessary to consume it.

**Graph Data Format:** We propose to represent the computation graph in a **JSON structure** containing:

* a list of **nodes**, and
* a list of **edges** between nodes.

Each **node** will have an `id` (unique identifier, e.g. the column name or an internal GUID), a human-readable **label** (likely the column name or an expression), a **type** (such as `"input"` for base input columns vs `"computed"` for derived columns), and a **data** payload with metadata (source code location, formula, sample values, etc.). For example, a node might look like:

```json
{
  "id": "net_premium",
  "label": "net_premium = gross_premium - expenses",
  "type": "computed",
  "data": {
    "formula": "gross_premium - expenses",
    "dependencies": ["gross_premium", "expenses"],
    "source_location": "model.py:42",
    "plugin": null,
    "dtype": "float",
    "value_sample": 500.0
  }
}
```

Edges are simpler, each defining a directed link from a dependency node to a dependent node (e.g. `{ "source": "gross_premium", "target": "net_premium" }`). An edge essentially corresponds to a formula reference: here it denotes that `net_premium` depends on `gross_premium`. The complete JSON might have an entry for every column (and intermediate) and edges for all relationships. This JSON is easily ingestible by front-end libraries. **React Flow**, for instance, expects an array of node objects and an array of edge objects to construct an interactive DAG. We can readily map our format to that. By including rich metadata in nodes, the front-end can display tooltips or side panels – for example, when a user clicks on a node, the UI could show the formula and perhaps the first few values or shape of that column.

**Alternatives:** Another common format is **GraphViz DOT** files. GraphViz is excellent for static visualization – indeed, Dask’s `.visualize()` function outputs GraphViz diagrams by default. We can support DOT or **Mermaid** (for Markdown embedding) as export options as well. A DOT file could list each node with a label (which could include the formula) and draw arrows for dependencies. This is useful for quickly generating a PDF/PNG of the model graph or embedding it in docs. However, DOT lacks an easy way to encode extensive metadata per node beyond the label, and it’s not interactive. **JSON (node-edge list)** is more flexible for programmatic use (especially for web UIs or further analysis), whereas **DOT/Mermaid** are convenient for documentation. Our design will likely implement a core graph representation (e.g. a NetworkX directed graph or just our list of `TracedOperation` nodes with dependency lists) and provide exporters: one to JSON, one to DOT. This covers both needs.

**Integration with React Flow:** To integrate with a library like React Flow, we must consider positioning and presentation, though those are front-end concerns. We will ensure each node has a stable `id` (we can use column names directly as IDs since Gaspatchio column names, once sanitized via issue #49, are valid identifiers and unique). For intermediate (non-materialized) nodes, we will generate unique names (e.g. the variable name if available, or a synthesized name like `_expr1`). The JSON will be consumed by the React app, which can then allow pan/zoom, rearrangement, and clicking nodes to view details. We will **not** implement the UI logic, but we document the JSON schema clearly so that front-end developers (or even actuaries using Python notebooks) can utilize it.

As an example, here’s a conceptual excerpt of an **emitted JSON graph** for a small model:

```json
{
  "nodes": [
    { "id": "policyholder_issue_age", "label": "policyholder_issue_age", "type": "input" },
    { "id": "term_offset", "label": "term_offset", "type": "input" },
    { "id": "issue_age", "label": "issue_age = policyholder_issue_age + term_offset", "type": "computed" },
    { "id": "year", "label": "year", "type": "input" },
    { "id": "age", "label": "age = issue_age + year - 1", "type": "computed" },
    { "id": "premium_double", "label": "premium_double = age * 2", "type": "computed" }
  ],
  "edges": [
    { "source": "policyholder_issue_age", "target": "issue_age" },
    { "source": "term_offset", "target": "issue_age" },
    { "source": "issue_age", "target": "age" },
    { "source": "year", "target": "age" },
    { "source": "age", "target": "premium_double" }
  ]
}
```

In this toy graph, **input nodes** (`policyholder_issue_age`, `term_offset`, `year`) have no incoming edges (they originate from data), intermediate `issue_age` is computed from two inputs, etc. A React Flow UI could render these as boxes with arrows, and by clicking “premium\_double” one could highlight the chain back to the inputs. The node labels include formulas for clarity. If a node had a plugin origin or other metadata, the front-end could show it on hover (since our JSON `data` field includes that info).

By supporting **multiple serialization formats**, we future-proof the system. For instance, a future enhancement might generate a **GraphViz image with values** overlay (issue #50 even suggests GraphViz/Mermaid output with values). Because our graph data includes sample values, we could populate node labels like `net_premium\n= gross_premium - expenses\n(1200 - 700 = 500)` for a specific case. That could produce a self-contained diagram illustrating the calculation flow. This is tangential, but underscores that capturing the graph once enables many presentation forms.

## 4. Insights from Other Graph-Based Frameworks

We examined how analogous systems capture and introspect computation graphs to guide our design, borrowing good ideas and avoiding pitfalls:

* **PyTorch (Dynamic Computational Graphs):** PyTorch’s autograd engine constructs a graph of operations dynamically as tensor operations are executed. Each `Tensor` keeps references to the function that produced it (`grad_fn`) and the tensors that function depends on (`next_functions`). This is conceptually similar to Gaspatchio capturing each column’s producing expression and linking to inputs. PyTorch demonstrates the **power of dynamic graphs** – you can use normal Python control flow and still build a graph on the fly. Gaspatchio likewise lets actuaries write regular Python (including loops, ifs, etc.), and our runtime proxies capture the resulting graph without static compilation. One lesson from PyTorch is the importance of **naming and introspection tools**. In PyTorch, graph nodes (operations) are not explicitly named by the user; debugging the graph often requires external tools (e.g. `torchviz`) which generate GraphViz visuals, but these can be hard to interpret as they show low-level ops and memory addresses. We aim to improve on this by using **meaningful names** (column aliases or user-defined variable names) for graph nodes and by providing built-in visualization/trace tools in Gaspatchio itself. Another insight: PyTorch only tracks operations if `requires_grad=True` (for performance). Similarly, we only capture the Gaspatchio graph in *debug/tracing mode* – if the user doesn’t need it, we avoid overhead (mirroring PyTorch’s lazy graph construction when needed). In summary, PyTorch’s approach validates our use of operator overloading to build graphs dynamically, but cautions us to **provide user-friendly introspection** (clear naming, organized graphs) since raw dynamic graphs can be opaque.

* **Dask (Task Graphs):** Dask builds a computation graph of tasks to execute computations lazily and in parallel. Its task graphs are explicitly introspectable – represented as dictionaries or NetworkX graphs – and Dask provides a `visualize()` method to produce a graph image. Notably, Dask can render the graph **before and after optimization** to show how tasks were fused. This concept applies to Gaspatchio: in optimize mode, our internal execution might fuse operations (like combining multiple column assignments into one Polars query). We should still expose the *logical* graph of the user’s model (analogous to Dask’s “high level graph”) for clarity, but we might also indicate where optimization fused steps (like Dask’s optimized graph) if that’s relevant for performance debugging. Another idea from Dask is offering both GraphViz and interactive HTML graph outputs – which we plan to emulate with DOT export and JSON for React Flow. Dask’s use case highlights the value of graph visualization in identifying bottlenecks or unnecessary dependencies. In Gaspatchio, an actuary or developer might use the graph to spot an unexpected dependency (e.g. a formula using a wrong input) or a calculation that could be simplified. One thing to avoid: Dask graphs can become very large and hard to read for big computations (GraphViz struggles with >100 nodes). Gaspatchio models could have dozens of columns, but typically not thousands of interconnected tasks, so graphs should remain manageable. We will still allow filtering or focusing on a subset of nodes (perhaps generating subgraph for a particular output of interest) to keep diagrams comprehensible.

* **Excel Formulas:** Excel’s “graph” of computations is implicit in cell formulas. Each formula directly lists its precedents (by cell references), forming a static DAG of dependencies. Excel provides **trace arrows** and a step-by-step evaluator to help users follow these links. The simplicity of Excel’s model is something we want to preserve: **each Gaspatchio column formula should be human-readable and reference other columns by name**, just like Excel formulas reference other cells by name. By implementing the variable-based column access from issue #49 (so formulas look like `net_premium = gross_premium - expenses` instead of cryptic DataFrame syntax), we get very Excel-like formulas in our traces. We will adapt Excel’s idea of interactive tracing: one can click from a result to its inputs and so on. Also, Excel’s *Evaluate Formula* feature shows the formula as text and successively replaces parts with values – our `CalculationTracer` essentially replicates this in a textual form. One thing to **avoid** from Excel: spreadsheets often hide complex logic in opaque cells or named ranges; Gaspatchio can do better by attaching rich context (units, descriptions, source code) to each node. Also, Excel doesn’t natively provide a global view of the formula network (you manually click around); in our design, we provide an explicit graph that can be visualized as a whole, which is an advantage. In short, Excel’s user-centric transparency guides our output format and feature set, but we go beyond Excel by making the entire model graph explicit and exportable.

* **Other References:** Many frameworks (TensorFlow, SQL query planners, Airflow, etc.) build DAGs for computations or tasks. TensorFlow (in static graph mode) required users to manually define a graph before running, which made debugging difficult – Gaspatchio intentionally avoids that by building the graph dynamically *from actual execution* in debug mode. Airflow and similar workflow engines label nodes (tasks) clearly and allow rich metadata, which we have mirrored by designing detailed node metadata (next section). The common theme is to capture enough information in the graph so that a user or developer can reason about the workflow without diving into low-level code. We apply that theme here for actuarial formulas.

In conclusion, these frameworks reinforce the approach of **runtime graph capture with minimal intrusion on the user**, plus the need for first-class tools to examine the graph. Gaspatchio’s design stands on the shoulders of these systems, combining PyTorch’s dynamic capture, Dask’s introspection, and Excel’s user-friendly formula view to deliver a best-in-class traceability feature.

## 5. Approaches to Graph Capture: AST vs Proxies vs Tracing

Capturing a computation graph from user-defined calculations can be done in different ways. We considered three main approaches:

**A. Static AST Parsing/Compilation:** Parse the user’s model code (Abstract Syntax Tree) ahead of execution to identify all operations and build a graph. This would mean treating the model function somewhat like a formula script – we’d examine assignments and function calls to see how columns are derived. While this approach can yield a complete graph *statically*, it has major drawbacks:

* It undermines debuggability. Gaspatchio initially tried an AST-based DSL and found it made debugging hard: actuaries couldn’t use standard Python debugging tools when the logic was transpiled behind the scenes.
* It struggles with dynamic Python features. If the model has loops, conditionals, or uses external libraries, a static analyzer might not capture the real execution flow or could misinterpret it.
* Implementing a full Python AST interpreter for our DSL is complex and hard to maintain (as noted in alternatives considered for issue #49, dynamic injection was rejected for similar reasons).
* The static approach conflicts with Gaspatchio’s dual-mode philosophy. We would, in effect, be creating a separate “compiled” path for optimize mode, duplicating logic. This risks inconsistencies between debug and optimize results, violating the principle that the “same model code works in both modes”.

Because of these issues, we lean away from pure static AST parsing. It was exactly to overcome AST limitations that Gaspatchio introduced the Python-native approach with runtime tracing. We want to maintain that flexibility.

**B. Runtime Proxies (Operator Overloading):** This is the approach currently in use and which our design extends. By overloading operations on `ActuarialFrame` and column proxies, we intercept column creation at runtime. For example, `ColumnProxy.__add__` returns an `ExpressionProxy` (holding a Polars expression and no immediate execution). The ActuarialFrame’s `__setitem__` is overridden to capture assignments. Essentially, we piggyback on Python’s execution: when the model function runs, it uses our proxy objects, and those proxies log the operations into our graph structure instead of producing final values directly (unless in debug mode where they also compute values). This method has several advantages:

* **Faithfulness:** We capture exactly what happened during execution, reflecting any dynamic decisions. If the code has an `if` that changes which columns are computed, the graph will represent whatever path was taken for given inputs.
* **Minimal user impact:** The user writes normal Python (with minor syntax enhancements from #49). There’s no need for them to annotate or stage computations explicitly. From their perspective, nothing magical is happening – which aids trust and adoption.
* **Dual-mode alignment:** In debug mode, our proxies can execute step by step (producing immediate results), whereas in optimize mode we can delay execution. The tracing decorator in Gaspatchio already handles switching between these modes by toggling a tracing flag and collecting ops in optimize mode. Thus, one code path can serve both, ensuring consistency.
* **Minimized overhead:** When tracing is off, the proxies can default to acting like normal (or simply not used), so optimize mode without tracing incurs no slowdowns. We’ve seen in tests that when `_tracing=False`, the append-to-graph function returns immediately and the loop of 1000 ops took <0.1s.
* **Minimized implementation complexity:** We do need to implement proxies for various operations (addition, multiplication, method calls like `.floor()`), but Gaspatchio has already established this pattern (with concrete proxy classes for domain-specific operations to preserve IDE support). Extending proxies to capture dependency info is straightforward.

One challenge with proxies is ensuring we don’t miss any operation. We must override all relevant operators and functions for ColumnProxy/ExpressionProxy. Gaspatchio covers many (basic arithmetic, unary functions, plugin calls via wrapping them to return expressions, etc.). If the user uses an unanticipated operation, it might execute without being traced. For example, if they convert to NumPy array mid-way (PyTorch has a known issue where switching to NumPy breaks the grad graph), we’d lose tracking. We will document that using supported vectorized operations is required for full traceability (which aligns with best practices anyway).

Another consideration: capturing **intermediate variables** (issue #49) with proxies. In the earlier example, `issue_age = policyholder_issue_age + term_offset` uses proxies, but since no `af[...]` assignment occurred, our graph capture via `__setitem__` wouldn’t log it. One runtime approach could be to detect when an ExpressionProxy is assigned to a Python name in the model function’s local scope – perhaps using Python’s frame inspection or a custom `__setattr__` on a special context object. Python does not easily allow intercepting plain variable assignment. However, since the static code generator in #49 forces the user to import all column proxies in the model module, we might instrument the model function via a decorator that scans local variables after execution. For instance, after running the model function in debug mode, we could inspect `locals()` for any `ExpressionProxy` objects that were created and not immediately assigned to the frame. These could then be added to the graph as intermediate nodes. This is a bit hacky but feasible. Alternatively, we accept that intermediate Python variables won’t appear as separate nodes unless the user explicitly creates a column. Given that one of the selling points of #49 is cleaner syntax (and actuaries often will directly assign final results to `af[...]` using expressions that combine those variables), it may suffice to capture the final relationships. We’ll weigh this trade-off: capturing every intermediate might clutter the graph, but it provides a more Excel-like breakdown. A compromise is to include intermediate proxies in the graph **only if they are subsequently used in an `af[...]` assignment** – that indicates they were meaningful.

**C. Bytecode Tracing / Debug Hooks:** Another approach would be to use Python’s inspection capabilities (e.g. `sys.settrace` or executing the function in a custom `Frame` object) to intercept operations. For example, one could trace all attribute access and function calls, and detect when `ActuarialFrame.__setitem__` is invoked or when certain global variables (column proxies) are read/written. This approach is generally low-level and complex. It can record every step of execution (even non-DSL steps), which creates a lot of noise and overhead. It would be akin to writing a debugger that watches the bytecode for certain patterns. Given that we have a clean proxy-based strategy, using a tracing hook would be overkill and could slow down execution significantly. **Bytecode manipulation** (like rewriting the function to inject tracing calls on the fly) is similarly risky and hard to maintain. Gaspatchio’s emphasis on keeping things “Python-native” suggests we shouldn’t deviate into such territory. We prefer the explicit but controlled approach of proxies and decorators to implicit bytecode hacks – it’s more transparent for developers working on Gaspatchio and easier to reason about.

**Summary of Trade-offs:**

* *Static AST:* Best for static analysis or if we wanted to generate an IR for heavy optimization. But it conflicts with interactive debugging and dynamic usage. We sacrifice it to favor explainability and simplicity.
* *Runtime proxies:* Aligns perfectly with our dual-mode design and gives us the needed info at the right time. Slight overhead in debug mode is acceptable; offers a single source of truth for both execution and graph. This is our chosen method.
* *Tracing hooks:* Powerful in theory, but not needed given proxies. Would complicate the system and possibly slow it down without clear benefit.

Gaspatchio has already made a strategic decision in this direction – the DSL redesign was explicitly to *capture Python operations in a graph while running them*. Our design doubles down on that, expanding what is captured (metadata, values) but not fundamentally changing the capture method. By doing so, we ensure that the **debug experience remains Pythonic** (you can step through code line by line in debug mode, because we are literally executing that code, not a pre-compiled AST). At the same time, **optimize mode can leverage the captured graph** to do vectorized computation in Rust/Polars for performance. We just need to carefully manage when we collect values or not, as discussed.

Finally, note that Gaspatchio’s **production-readiness principle** demands that even with these tracing capabilities, a production run should be as fast as possible (only a small constant overhead if tracing is simply off). We will provide configuration (like a flag `trace=True` or the `--trace-values` CLI option) to enable the full graph/value capture when needed for a run. In everyday large batch runs, this would be off, keeping the system “default fast”. But when an actuary or developer needs to diagnose something, they can run a single policy or a sample through in debug mode with tracing on and get the full picture, very much analogous to how one might use a debugger or verbose logging only in development.

## 6. Node Metadata to Track for Traceability

Each node in the computation graph should carry sufficient metadata to support explainability, debugging, and potential future features (like performance analytics or AI assistance). We propose to track the following for each `TracedOperation` node:

* **Column Name (Alias):** The name of the column as used in the model (`TracedOperation.alias`). This is the primary identifier for the node (and doubles as its label in diagrams). For intermediate variables that aren’t actual columns, this would be the variable name (if captured). Having the exact alias is also crucial for mapping the node to the result DataFrame column to fetch values.

* **Expression / Formula:** A representation of the calculation. We will store the Polars expression object (`TracedOperation.expression`) and possibly also a string of the original syntax. The string could come from either the expression’s AST or from source capture. In fact, we can capture the **source code snippet** corresponding to this operation using Python’s `inspect` module. In the tracing implementation, right when we append the operation, we can record the current file name, function name, and line number. Using that, we can retrieve the exact line of code (the issue #50 plan included storing `source_line` in metadata). This means the node can report: *defined in model.py line 42: `af["net_premium"] = af["gross_premium"] - af["expenses"]`*. This is extremely useful for debugging – it connects the graph back to the source code the actuary wrote, so they can quickly locate the formula. Our metadata will include:

  * `file_name` and `line_number`,
  * `function_name` (often the model function name, e.g., `main`),
  * `source_line` (the actual code text).

  If source is unavailable (e.g. running in an interactive console), we handle gracefully, but in most cases models are in scripts so this works. We will attach the source snippet (or a sanitized formula string) as part of node metadata.

* **Dependencies:** As discussed, we store a list of dependency identifiers (column names or node IDs) for each node. This could also be represented as edges externally, but including it in the node metadata helps when generating textual traces (so each node “knows” who its parents are). It also assists any algorithm that might do a topological sort or detect cycles (shouldn’t happen unless there’s a circular formula dependency, which we will document as unsupported).

* **Plugin/Origin Info:** If the operation was produced by a plugin function or special mechanism, note that. E.g., a node might have `origin = "plugin:fill_series"` or `origin = "assumption_table_lookup"` with perhaps the name of the table. This gives context beyond the formula itself. For instance, an actuary seeing `mortality_rate = assumption_lookup(...)` might want to know which table was used – we can include `"table": "CSO_table_2001"` in metadata. Essentially, any non-trivial transformation (like a table lookup or a vector filler) gets an annotation. This is analogous to Excel showing a UDF name in a formula – we show the plugin name in the formula string too, but metadata can carry details (like which parameters or version).

* **Data Types and Shapes:** Knowing the type of each column (integer, float, vector of length N, etc.) is useful for both debugging and display. We store the `dtype` of the result (and perhaps expected dtype if type-checking was done). For vector columns (List types in Polars), store the length or shape. In the code snippet, they record `value_shape = (num_rows, vector_length)`. Given Gaspatchio often deals with vector projections per policy, we define `vector_length` as the number of time steps if the column is a projection. If a column is a scalar (one value per policy) then vector\_length = 1 (or we mark it scalar). This metadata helps the trace UI know, for example, that it should allow selecting a time index for this column because it’s vectorized.

* **Actual Values (Samples):** To support the Excel-style value tracing, we attach representative values. Storing **all** values for every policy could be huge, so by default we keep either none or small samples. We can store:

  * For scalar columns: perhaps the first few values (say first 3 policies’ values), just to give a sense, and maybe the min/max for sanity checks.
  * For vector columns: we can store a small sample vector (like for the first policy, store the first 5 periods and last period as they do) or summary statistics of the vector (like an average over time, etc.). But to fully trace a specific policy, the `CalculationTracer` will dynamically pull the needed values from the DataFrame, so we don’t need to store every value for every node upfront. We just need enough to support quick introspection or UI previews. Perhaps the most recent plan is to store *for each node, if value tracking is enabled, the actual computed series for each node for at least the policy that was run* (in single-policy runs). In a multi-policy context, we might not store values for all policies by default, but could on demand.

  Our design leans on **lazy value retrieval**: we have the final DataFrame, so if an interactive UI wants the value of node X for policy Y, it can query the DataFrame (which is likely small or an index lookup). We need to make sure our graph data structure can link back to the DataFrame (e.g. know the DataFrame or dataset it came from). In the `CalculationTracer`, we’ll keep a reference to the result DataFrame to fetch values as needed. This avoids storing large arrays in the graph, keeping memory usage reasonable.

  In summary, node metadata will include `value_sample` (some sample or representative slice) and possibly a pointer or key for looking up full values (for instance, the node’s alias is the DataFrame column name, so that’s enough to retrieve values given a DataFrame).

* **Execution Stats:** It can be useful to know performance details for each operation. For example, how long did computing this column take? Was it executed via Polars vectorization or did it fall back to Python? How many rows were processed? Gaspatchio can collect some of this. In debug mode, since each column is computed one by one, we could time each `af.__setitem__` operation and attach a duration (this might slow things, so perhaps only if a verbose flag is on). In optimize mode, Polars runs the whole query, so per-column timing is not directly available (Polars does not generally report time per expression). However, we might infer relative cost by looking at the Polars plan or using Polars profiling features if any. This might be an advanced feature; initially, we can at least mark if an operation was executed in optimized context vs Python. For example, if a user-defined Python function couldn’t be JIT-compiled and so ran in Python, we mark that node with `exec_mode="python_fallback"` (Gaspatchio already logs such warnings). Also, storing the order of execution can be useful (though it’s basically the index in the graph list). If needed, we could add a sequence number or timestamp for when it executed.

For now, the focus is on **traceability** rather than performance tuning, so the key metadata are those that help explain the calculation. The test `OperationMetadata` in Gaspatchio confirms capturing of **file, line, function, source**, and our design adds dependencies, values, etc., as outlined in issue #50. We will implement `OperationMetadata` as a dataclass with fields like: `alias`, `expr_repr`, `deps`, `file`, `line`, `func`, `source_line`, `plugin`, `dtype`, `shape`, `sample_values`, `exec_info` etc. This metadata is stored in each `TracedOperation` node and will be included in the JSON export (under the node’s `data` field as shown in Section 3).

Tracking this metadata greatly enhances **explainability**: an error message can show the failing column along with the original code line; a trace UI can display context like “defined in function X at line Y” to orient the user; and documentation generators or even AI assistants can use this info to answer questions about the model (for instance, an LLM could use the structured graph to explain the model’s logic in natural language, aligning with the principle of being “LLM native” and having structured outputs for AI).

## 7. Graph Data Structures & Serialization Formats

Internally, we will represent the graph as a collection of `TracedOperation` nodes (perhaps stored in a list as now, or in a dictionary keyed by alias). The **edges** can be derived from each node’s dependency list, so an explicit separate edge list is not strictly necessary in memory – but for algorithms like cycle detection or ordering, constructing an adjacency list or matrix is trivial from the nodes. We may implement a small utility that builds a NetworkX directed graph from our nodes when needed (for example, to leverage NetworkX algorithms or to export in various formats easily).

When it comes to **emitting the graph externally**, we already decided on JSON for primary use, and GraphViz DOT as a secondary option:

* **JSON Output:** We will create a function like `export_graph(format="json") -> str` that returns a JSON string (or Python dict that can be dumped to JSON). This will iterate over each node in `af._computation_graph` and serialize it. We must ensure non-serializable objects (Polars expressions, etc.) are converted to strings or omitted. Likely we include the `expression` as a string representation for readability. The `values` (if any) can be serialized if they are basic Python types (ints, floats, lists), but large arrays should be avoided. We'll include only sampled values as discussed. The output will follow the structure shown earlier (with `nodes` and `edges` lists). This JSON can be written to a file or returned via an API for a web app to consume.

* **DOT Output:** The `export_graph(format="dot")` will produce a DOT language string. Each node can be a DOT node, with label attribute containing perhaps the node’s alias and maybe a shortened formula. We might not include values in the label to keep it concise (or we could optionally). Edges are then “alias -> dep” for each dependency relation. Since we have unique aliases, they can serve as node names in DOT (though we should sanitize them to be valid identifiers, e.g. no spaces – but #49’s sanitization already removes spaces, and we can wrap labels with quotes if needed). We could also cluster nodes or color them (like input vs computed) in DOT for clarity. These are cosmetic details left to implementation.

* **Mermaid Markdown:** As an extension, we could support Mermaid JS format which is popular in Markdown documents for embedding diagrams. Mermaid can also show DAGs with a simple syntax. This would be similar to DOT in content but easier to embed in docs or wikis. We won’t delve deep here, but mention that since we can convert to DOT, converting to Mermaid is also straightforward.

* **Alternate Graph Formats:** The internal graph could be made to conform to a **specification like Dask’s task graph spec** (which uses a dict of tasks mapping to dependencies), but our graph is much simpler (each node is just a formula, not an arbitrary Python callable). A dict mapping `alias -> (expr, deps)` is essentially what we have. We could expose that directly for Python users who want to introspect the graph programmatically. For example, `af.get_computation_graph()` could return a dict:

  ```python
  {
    "gross_premium": {"expr": ..., "deps": []},
    "expenses": {"expr": ..., "deps": []},
    "net_premium": {"expr": "gross_premium - expenses", "deps": ["gross_premium","expenses"]}
  }
  ```

  This is easy for a developer to loop through or analyze. But for most end users, the JSON or a nice printed format is more useful. Still, having a machine-readable form (like a Python dict or JSON) aligns with openness – you aren’t locked into a proprietary structure.

**Ensuring Completeness:** When serializing, we must ensure that **all relevant nodes are included**. In debug mode, `_computation_graph` likely contains all assignments made within the model function. In optimize mode, it’s similar (since we captured them then executed in bulk). But what about *input columns*? If the input data has columns that are never touched by the model, they might not appear in the graph. That’s fine – those don’t need to be visualized unless for completeness of data lineage. We could include input columns as nodes with no parents if we want the graph to have a root for each original input. This might clutter the graph if there are many unused inputs, so maybe we include only those actually referenced by some computation. Any input that ends up being used will appear in some dependency list and we can create a node for it (with deps = \[]). We should mark such nodes as type `"input"`.

**Graph Cycles:** Ideally, there should be none (models shouldn’t have circular references: that would be like an Excel circular formula which is invalid or requires iterative solving). We can include a check in debug mode to detect if a new assignment creates a cycle (e.g. user accidentally uses a column that depends on the one being computed). We can detect that by doing a DFS from the node’s deps to see if we reach itself. This check is easier with an explicit adjacency structure. If found, we’d log or error out (failing fast with a clear message). This ensures the graph remains a DAG which is important for correct visualization and interpretation.

**Scalability:** For models with hundreds of columns, the JSON and graph might be quite large (but still manageable). We should consider an option to **filter or focus** the export. For example, `export_graph(columns=["net_premium", "age"])` could output only the subgraph needed to compute those columns. This subgraph extraction is straightforward given we have dependency lists. This could be useful if an actuary only cares to visualize a portion of the model (e.g., the cash flow calculation part and not other interim calculations).

The design’s emphasis on JSON and DOT aligns with the suggestion from issue #50’s future enhancements and the project’s need to integrate with web dashboards (where JSON is king). It also satisfies the requirement to not implement a front-end but make it *possible* – by handing off well-structured data.

By delivering the graph in these formats, we adhere to **production-readiness** because we allow this feature to be used in various environments (Jupyter notebooks, web apps, CI pipelines for documentation generation, etc.) with minimal friction. For instance, a CI job could run a model in debug mode with tracing on and output a DOT file which is then rendered as an SVG artifact for model documentation. Or an actuary could import the JSON in a Jupyter notebook and use Plotly or networkx to visualize it. The key is the data is accessible and structured.

## 8. Design Trade-offs & Alignment with Gaspatchio Principles

Throughout this design, we have balanced **explainability** and **debuggability** with **performance** and **maintainability**. Let’s highlight how our recommendations uphold Gaspatchio’s core principles:

* **Explainability:** The captured computation graph, combined with formula/value tracing, makes the model’s workings transparent. Users can literally see how each output is built up from inputs, akin to reading a flowchart or an Excel model. This is a huge leap in model explainability and trust. It addresses a common request from actuaries to “show the formula behind that number”. By including actual values in traces, we deliver **“Excel-like transparency”**, fulfilling the promise that Gaspatchio models are not black boxes but readable, auditable processes. Moreover, including source code references in metadata means that any stakeholder can trace a number back not just to inputs but to the exact line in the model code, bridging the gap between business domain and implementation.

* **Debuggability:** Our design cements Gaspatchio’s strength in debug mode. Actuaries can develop models in debug mode with full Python capabilities, and now also leverage the computation graph to debug logical errors. For example, if a value looks off, the trace will reveal if an incorrect column was used or a formula applied out of order. The system also captures context like source lines and will integrate with error handling: if an error occurs in computing a column, we have its graph node which knows the code location and dependencies, enabling more informative error messages (e.g., “Error in calculating `net_premium` (defined in model.py line 42): division by zero, inputs were ...”). This echoes Gaspatchio’s contextual error handling approach and will improve it further. Additionally, by capturing intermediate computations (even if not output), the design allows debugging step by step as in Excel (you can inspect the value of “issue\_age” even if it wasn’t a final output, as long as it was traced). This aligns with the principle of meeting actuaries *“where they are”* – giving them familiar debugging aids in the new system.

* **Production-Readiness:** We have kept performance in mind. The graph capture and value tracing can be **enabled or disabled** according to need. In high-performance production runs, one would run in optimize mode with tracing off, incurring minimal overhead (just a check flag on each **setitem**, which is negligible). Thus, our enhancements do not slow down the mission-critical path. On the other hand, the tools are available in production if one needs to run a trace on a specific case (e.g., debugging a policy that produces NaNs). The design also ensures the same model code yields the same results in both modes – the graph is captured from the actual execution path, so we aren’t at risk of discrepancies. We explicitly choose runtime capture to avoid a separate static compilation that might diverge, thereby maintaining consistency and reliability. The ability to export the graph means the system plays well with enterprise workflows: e.g., the JSON could be saved as an artifact after each model run for audit purposes, or visualizations could be integrated into reports. This enhances the **governance and auditability** of models in production – a regulator or reviewer could be given the computation graph of a model run to verify logic, which is often impossible with pure code or even with Excel unless one inspects cell by cell.

* **Maintaining Python Ecosystem Compatibility:** By not requiring custom languages or heavy AST transforms, we continue to allow use of *“all of the Python ecosystem/libraries available”*. Our graph capture won’t interfere with using libraries like NumPy, SciPy in the model – we either convert those to expressions or treat them as black-box functions in the trace (possibly with a note that a custom function was used). The key is we don’t restrict modelers in the name of traceability; we instrument behind the scenes instead. This design is in spirit with Gaspatchio’s approach to give flexibility first, then optimize or trace as needed.

* **IDE & AI Integration:** The structured graph and metadata make the system **AI-friendly**. As noted, structured outputs enable LLMs to reason about the model. An AI assistant could use the graph to answer “Explain how net\_premium is calculated” by traversing it – effectively reading off the trace we can generate. Also, since we keep type information and source lines, an AI could potentially suggest fixes (e.g., “it looks like you used `expenses` but maybe you meant `expense_load` – similar to error suggestions Gaspatchio already envisions). Our design doesn’t explicitly delve into AI, but it’s an ancillary benefit.

* **Complexity vs Benefit:** We do add some complexity (more data structures, more logic in tracing), but we do so in a self-contained way. The core execution and optimization engine (Rust/Polars backend) remains the same; we are layering on a Python-side trace mechanism. If tracing is off, the model essentially runs as it did before. So we haven’t endangered the core. The benefits – better debugging, user confidence, easier onboarding from Excel – are huge, more than justifying the additional components.

**Trade-offs Recap:** One trade-off we accept is memory usage for storing graph and sample values. For a model with, say, 100 computed columns and 100k policies, storing even a few values per column is minor, and storing the graph structure itself is trivial. If memory ever became a concern, we could make value capture depth configurable (issue #50 suggests limiting trace depth or number of time points). Another trade-off is that intermediate variable capture (issue #49) isn’t fully automatic – our design suggests a partial solution or requiring explicit action to capture those. We judged that fully parsing every local variable would complicate things, and opted to primarily capture through the frame assignments (since ultimately anything important should flow into a frame column). This keeps the implementation simpler, though it means if an actuary writes a complex formula in a single line, the trace might show it as one node rather than breaking it into sub-steps. We think that’s acceptable and analogous to how Excel can have a single cell with a long formula – you can still trace through it via sub-expressions. If needed, users can break formulas into multiple assignments to get more granular trace nodes.

In conclusion, the proposed design strongly reinforces Gaspatchio’s goal of being *“both powerful and pleasant to use”*. It brings a new level of introspection to actuarial modeling that is on par with, or even exceeds, Excel’s capabilities, all while maintaining high performance and a seamless developer experience. By clearly delineating debug vs optimize behavior and capturing rich metadata, we ensure the model is as easy to *debug* as it is to *run at scale*. This will make Gaspatchio models highly trustworthy and easier to validate, which is crucial in the actuarial domain.

## Appendix: Integration with React Flow – Example Graph Structure

To illustrate how the emitted graph could be used in a visualization tool, consider the following simple model snippet and its graph:

```python
# model_calculation.py
from gaspatchio_core import ActuarialFrame
from .model_columns import *  # assume this brings in base columns as variables

def model(af: ActuarialFrame) -> ActuarialFrame:
    issue_age = policyholder_issue_age + term_offset
    af["age"] = issue_age + year - 1
    af["premium_double"] = af["age"] * 2
    return af
```

**Emitted Graph JSON:** After running this model with tracing on, Gaspatchio might produce a JSON like:

```json
{
  "nodes": [
    { "id": "policyholder_issue_age", "type": "input", "label": "policyholder_issue_age", 
      "data": { "dtype": "int", "source": "model_points.csv", "dependencies": [] } },
    { "id": "term_offset", "type": "input", "label": "term_offset", 
      "data": { "dtype": "int", "source": "model_points.csv", "dependencies": [] } },
    { "id": "issue_age", "type": "computed", "label": "issue_age = policyholder_issue_age + term_offset", 
      "data": { 
         "formula": "policyholder_issue_age + term_offset", 
         "dependencies": ["policyholder_issue_age","term_offset"],
         "source_location": "model_calculation.py:5",
         "value_sample": 42  } },
    { "id": "year", "type": "input", "label": "year", 
      "data": { "dtype": "int", "source": "model_points.csv", "dependencies": [] } },
    { "id": "age", "type": "computed", "label": "age = issue_age + year - 1", 
      "data": { 
         "formula": "issue_age + year - 1", 
         "dependencies": ["issue_age","year"],
         "source_location": "model_calculation.py:6",
         "value_sample": 41  } },
    { "id": "premium_double", "type": "computed", "label": "premium_double = age * 2", 
      "data": { 
         "formula": "age * 2", 
         "dependencies": ["age"],
         "source_location": "model_calculation.py:7",
         "value_sample": 82  } }
  ],
  "edges": [
    { "source": "policyholder_issue_age", "target": "issue_age" },
    { "source": "term_offset", "target": "issue_age" },
    { "source": "issue_age", "target": "age" },
    { "source": "year", "target": "age" },
    { "source": "age", "target": "premium_double" }
  ]
}
```

In this JSON:

* **Input nodes** (`policyholder_issue_age`, `term_offset`, `year`) have no dependencies and are labeled simply by name (we include their origin “model\_points.csv” hypothetically to denote they come from input data).
* **Intermediate node** `issue_age` is marked computed and shows the formula it was calculated with. It depends on two inputs. We included a sample value (42) for demonstration (say, for a particular policy).
* **Computed nodes** `age` and `premium_double` depend on prior nodes as expected. Each has the code line it came from and a sample result.

A React Flow application can take this JSON and create visual nodes for each. For instance, it might display each node box with the `label` (so the formula is shown for computed nodes). The edges array directly tells it how to connect them. Because we have IDs and dependency lists, the tool can allow the user to highlight all predecessors of a node (e.g., hover on “premium\_double” could highlight the path back to inputs). The `data` field can be used to show more info on click (like a sidebar with “Defined in model\_calculation.py line 7” and “Sample value for Policy 1: 82”).

This structured approach is consistent with how **Cytoscape** or **React Flow** consume data. It does not dictate any specific layout; the front-end would typically use an automatic DAG layout or manual positioning. We do not output coordinates – those would be added by the front-end if it saves a user arrangement.

Overall, this example shows that with a fairly straightforward JSON, we can empower a visualization library to present the entire model graph interactively. This meets the requirement of supporting tools like React Flow and provides a foundation for any other integration (even non-graphical, such as exporting to a knowledge graph or database for auditing).

By designing the data schema in tandem with our graph capture, we ensure that **what we capture is immediately usable** for visualization and analysis, closing the loop from raw model code to user-friendly diagram. This is the final piece that truly makes Gaspatchio’s computation graph a practical asset for traceability, not just an internal structure.

**Sources:** The design draws on Gaspatchio’s existing architecture decisions and enhancements proposed in issues #49 and #50, ensuring we build on a solid foundation. The approach also resonates with practices in PyTorch (dynamic graph capture), Dask (graph visualization), and Excel (formula auditing), adapted to Gaspatchio’s unique dual-mode DSL environment. The end result is a comprehensive plan to make every number in an actuarial model explainable through an accessible computation graph.
