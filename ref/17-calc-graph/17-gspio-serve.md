Great — I’ll write a design plan for the `gspio serve` CLI command that launches a web server to host a Next.js app for visualizing the calculation graph.

This plan will cover how to:

* Serve a Next.js frontend from FastAPI
* Handle policy\_id parameter for recalculation and dynamic updates
* Define and deliver the graph JSON structure needed by React Flow
* Offer user interaction to update the policy\_id
* Learn from related tools like spaCy’s Displacy, and stay aligned with your team’s principles

I’ll also suggest the cleanest full-stack dev flow and include some server setup hints for bundling static Next.js assets.
I’ll follow up shortly with the detailed plan.


# Design Proposal: `gspio serve` – Interactive Computation Graph Viewer

## Overview and Objectives

The `gspio serve` command will launch an interactive local web application that visualizes the **computation graph** of a Gaspatchio model. The goal is to give actuaries an Excel-like view of how each value is calculated – displaying formulas, dependencies, source code locations, and sample results for each node of the calculation. By running `gspio serve`, users can open a browser to see a graph of all computed columns (nodes) and their relationships (edges). Key features include:

* **FastAPI Web Server**: The CLI command starts a FastAPI server that serves a **Next.js** frontend. This single-page app visualizes the model’s computation graph using **React Flow** for an interactive nodes-and-edges diagram.
* **Static Frontend Assets**: The Next.js app (pre-built to static files) is served by FastAPI similar to how spaCy’s *displaCy* serves visualizations. FastAPI’s `StaticFiles` will mount the build output (HTML, JS, CSS) so that accessing the local server’s root URL loads the React app.
* **Computation Graph JSON API**: The backend provides an HTTP API (e.g. `GET /api/graph?policy_id=123`) that returns a JSON representation of the computation graph (nodes + edges). Each **node** includes metadata like the column name, formula/expression, source code location, and a sample value. **Edges** denote dependency links (e.g. node A depends on node B).
* **Policy-Specific Recalculation**: Users can specify a `policy_id` (either via a CLI option or within the web UI) to focus the graph on a single policy’s calculation. The backend will trigger a recomputation for that policy and update the graph JSON with that policy’s values. This allows **dynamic “what-if” exploration** – e.g., switching the policy ID shows how all node values change for that selection.
* **Full Graph View (Toy Model)**: Initially, the tool will display **all computed nodes** in the model’s graph (suitable for small or example models). In future iterations, we will support filtering or scoping the graph (e.g. show a subset of nodes or one sub-tree) to accommodate very large models.

By integrating with Gaspatchio’s existing calculation engine and tracing hooks, `gspio serve` will provide transparency into the model logic without requiring users to leave their familiar CLI workflow. This design aligns with Gaspatchio’s principles of *meeting actuaries where they are* (using Python/CLI tools they know) and *enhanced debugging/tracing* capabilities in debug mode.

## Serving the Next.js Frontend with FastAPI

A core task is to serve the React/Next.js frontend through the FastAPI server started by the CLI:

* **Next.js App**: We will develop a Next.js application (likely located in a `frontend/` directory of the repository) using React and React Flow. This app will be built into static files (using `next build && next export` for a static export, or a production build served as a static SPA). The output will include an `index.html` and static JS/CSS assets.

* **StaticFiles Mount**: In the FastAPI app, we’ll mount a `StaticFiles(directory=<build_dir>, html=True)` on the root path. For example:

  ```python
  from fastapi import FastAPI
  from fastapi.staticfiles import StaticFiles

  app = FastAPI()
  app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
  ```

  This means any request for the base URL (`/`) or any unknown path will serve the Next.js app’s `index.html` (enabling client-side routing if needed). FastAPI’s static file support will handle serving all the JS, CSS, and image files. We will ensure the static files are included in the Python package distribution (e.g. via `package_data` or similar) so that `gspio serve` works out-of-the-box.

* **Launch via CLI**: The Typer CLI (`gaspatchio_core.cli:app`) will get a new command `serve`. When invoked, this command will start the FastAPI server (likely using Uvicorn). For example, it may call `uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")`. We might default to localhost and a standard port, with options to override. On launch, it will log a message like “🚀 Serving Gaspatchio UI at [http://127.0.0.1:8000”](http://127.0.0.1:8000”). The server will continue running until interrupted (Ctrl+C), similar to spaCy’s displaCy server.

* **spaCy displaCy Parallel**: This approach is analogous to spaCy’s `displacy.serve`, which spins up a simple web server to visualize NLP dependency parses. Unlike spaCy (which directly injects HTML), our approach serves a full React app. This gives more flexibility for interactivity (e.g., user controls to select policy IDs, zoom/pan the graph, etc.), at the cost of needing a build step for the frontend. This trade-off is worthwhile given the complex visualization needs.

**Technical Consideration – Packaging**: We will include the built frontend assets in the Python package so that users don’t need to run a separate Node server. For development, we can allow an environment variable or CLI flag to use a *hot-reload dev server* (Next.js dev server) instead – but in production, `gspio serve` will use the static build. This keeps deployment simple (just the CLI command) and follows the principle of *meeting users where they are*, by not requiring additional infrastructure.

## Backend API Design for Graph Data

The FastAPI backend will expose endpoints to retrieve the computation graph and trigger recalculations. The primary endpoint will be:

* **`GET /api/graph?policy_id=<id>`** – Returns a JSON structure representing the computation graph for the specified policy. If `policy_id` is omitted or null, it could return the *base graph structure* (all nodes and edges, but without specific value samples). In the initial version, we might require a policy\_id to be specified (since value display is most meaningful for a single policy’s data). The response JSON will contain two main sections:

  ```json
  {
    "nodes": [ ... ],
    "edges": [ ... ]
  }
  ```

  **Node Format**: Each node will be an object containing details about one computed quantity (column) in the model. Example fields:

  * `id` (string): Unique identifier for the node, typically the column name or an expression alias.
  * `label` (string): A human-friendly label for display. This might be same as `id` initially (we can use the column name as the label).
  * `formula` (string): The formula or expression that computes this node’s value. We will use the expression captured by ActuarialFrame in debug mode. For example, it might show `premium_total = premiun * 12` (typo intended if present in code) or a Polars expression string. We will aim to show it in a format similar to the model code or a simplified expression.
  * `source` (object): Information about where this calculation was defined in the model code. Using the ActuarialFrame’s tracing metadata, we can include the file name and line number, and possibly the exact code line. For example: `"source": {"file": "model_calculation.py", "line": 27, "code": "af['premium_total'] = af['premiun'] * 12"}`. This helps users quickly locate the implementation of that formula.
  * `dependencies` (array of strings): The list of node IDs that this node depends on. For instance, `premium_total` would list `premiun` as a dependency. This will be derived by analyzing the expression for references to other columns. We can leverage Polars expression internals or parse the string for `col("X")` patterns to gather column names used. (If a node depends on base input fields, those fields will be included as nodes too – see **Including Input Nodes** below.)
  * `value_sample` (any JSON-serializable value): A sample of the calculated value for the selected policy. For scalar outputs, this could be the numeric value itself (e.g. `8` or `0.00008`). For vector outputs (like projections over time, stored as list/series), we will include a small sample or summary. For example, we might provide the first few periods and the last period of an array, plus the length. E.g.: `"value_sample": {"first_values": [0.00095, 0.00093, 0.00092, ...], "last_value": 0.00008, "length": 480}`. This gives insight into the shape of the output without sending the full vector of 480 items. In the future, more interactive drilling into vector data could be supported (see Appendix).
  * `type` (optional): The data type or shape of the node’s value (e.g. “scalar (float64)” vs “vector (length 480)”). We can get this from the ActuarialFrame’s type inference (`expected_dtype`) which is already captured for each operation. This is useful for understanding if a column is a list (vector) or single value, etc.

  **Edge Format**: Each edge will be a simple object defining a link from one node to another:

  * `source`: the ID of a dependency node
  * `target`: the ID of the dependent node (the one that uses the source in its formula)

  The edges can be derived directly from each node’s `dependencies`. For every `dep` in a node’s dependency list, we create an edge `{ source: dep, target: node.id }`. This yields a directed acyclic graph (it should be DAG if the model has no circular formulas, which we assume Gaspatchio prevents).

* **Other Endpoints**: In this initial design, a single `/api/graph` endpoint may suffice. The frontend can request the graph whenever needed (e.g., on initial load or when a new policy is selected). If needed, we could add:

  * `GET /api/policies` to list available policy IDs (for a dropdown in the UI). This can be done by querying the model points DataFrame’s ID column for unique values. However, if the data is huge, we might avoid listing all IDs. As a compromise, we could provide the first N or a random sample. For now, this is optional – the user might just input an ID manually.
  * `POST /api/recalculate` – an alternative to GET, where the request body supplies a policy\_id (and possibly other parameters in future) and the server returns the updated graph. But since the only parameter is policy\_id, a GET with query param is straightforward.

* **Performance**: The JSON size will depend on the number of nodes. For a toy model (small number of computed columns), this is negligible. If a model has hundreds of columns/nodes, the JSON could be large but still likely under a few hundred KB, which is fine for local use. We will ensure the API is only used locally (the CLI doesn’t aim to provide a hardened remote service), so minimal auth/security is required. By default, we’ll bind to `127.0.0.1` to avoid exposing data on a public interface unless explicitly intended.

## Integration with Existing Calculation Code

A crucial aspect is **reusing Gaspatchio’s existing model execution and tracing mechanisms**, rather than writing a separate calculation engine. We will leverage the same APIs currently used by `gspio run-model` and `run-single-policy`, ensuring consistency with how models are normally run. Key integration points:

* **ActuarialFrame and Tracing**: Gaspatchio’s `ActuarialFrame` (in debug mode) already captures each operation in a computation graph structure for tracing and error reporting. When in debug mode (`mode="debug"`), every time a column is assigned (`af["col"] = ...`), instead of immediately executing, the operation is stored in `af._computation_graph` as a `TracedOperation` object with metadata. This includes the column alias, the Polars expression, and an `OperationMetadata` (file, line, code snippet, etc.). We will take advantage of this: by running the model in debug mode, we can extract the list of `TracedOperation` from the ActuarialFrame to build our nodes.

* **Running a Single Policy**: Gaspatchio already provides `run_single_policy(config, policy_id)` for executing a model for one specific policy. Internally, this function:

  1. Loads the model code (imports the model function from the given file).
  2. Reads the model points data (as a Polars LazyFrame) using `read_model_points` utility.
  3. Filters the data to the specified policy\_id (by matching the ID column).
  4. Constructs an `ActuarialFrame` with that filtered data (honoring the `mode` in config).
  5. Runs the model function with the ActuarialFrame, then collects the results and metrics.

  We will mirror this process. Rather than duplicating logic, we can **call the same utilities**:

  * Use `ModelRunConfig` to hold model file path, data path, and ensure `mode="debug"` (we want debug mode by default for tracing).
  * Use `load_model_from_path` to get the model function object.
  * Use `read_model_points` to load the dataset (likely as LazyFrame).
  * Instead of calling `runner.run_single_policy` directly (which returns a `ModelRunResult` without exposing the internal graph), we will perform the steps ourselves to capture the graph:

    * Create `af = ActuarialFrame(data_lazy, mode="debug")`.
    * Invoke the model function with `af` (e.g. `dsl_run_model(model_func, af)` as the runner does).
    * After running, retrieve `af._computation_graph` which now contains the list of operations captured during the model run.
    * Call `result_df, profile_info = af.profile()` to execute the deferred computation and get the actual results. The `result_df` will be a Polars DataFrame (or at least a lazy result collected) with one row (for the single policy) and all output columns. We will also get `profile_info` (Polars execution timings etc., which we might not use in this feature, but could be logged or potentially displayed later for performance debugging).
    * At this point, `af._computation_graph` still holds the operations (the code does not automatically clear it after profile/collect). We can iterate over this list to build nodes as described. Each `TracedOperation` has `alias` (column name), `expression`, and `metadata` with source info. We’ll augment it with computed values from `result_df`.

  Using this approach ensures we reuse the **ActuarialFrame’s tracing system** (which was built for enhanced debugging) and the existing model loading logic. It avoids writing any custom parsing of the model code – we rely on the model actually running on real data. This also means the graph and values are accurate and reflect any runtime behavior (e.g. if certain branches are skipped or any dynamic logic, it will be captured).

* **Caching Model and Data**: To make interactive use snappy, we will **load the model and data once** at server startup, and reuse them for subsequent requests:

  * The model function (`model_func`) can be kept in memory after the first load. We only need to import the model file a single time (unless the user edits it externally – in which case a restart of `gspio serve` would be needed to pick up changes, which is acceptable).
  * The full model points DataFrame can be loaded into memory as well (or kept as a LazyFrame). Since we are likely focusing on one policy at a time, it may be efficient to load it eagerly into a Polars DataFrame and then filter by policy\_id in-memory. Polars filtering on an in-memory DataFrame is extremely fast (and the data is not huge in memory for a single policy slice). This prevents re-reading from disk on every selection. We do need to be mindful if the data is extremely large (millions of rows). In such cases, reading it fully might be heavy; however, Gaspatchio is designed for large portfolio runs, so it’s likely using Polars efficiently. We assume for debugging purposes, loading once is fine. We will document that `gspio serve` is meant for model development and debugging on reasonably sized data, not necessarily for the full million-policy production dataset at once (though it could handle it if memory permits).
  * The ActuarialFrame itself should be newly constructed per request (since it encapsulates state per run, including `_computation_graph`). We won’t reuse the same `ActuarialFrame` object across different policy selections; instead, for each API call we’ll make a fresh one with the filtered data. This avoids any leftover state. The model function (which likely adds columns to `af`) can be reused safely on a fresh frame.

* **Policy ID Input**: The CLI might allow an optional argument, e.g. `gspio serve <model.py> <points.parquet> --policy-id 123`. If provided, the server could use that as a *default selection*. For instance, it could immediately pre-compute the graph for that policy and the UI could load it by default. Alternatively, the CLI could simply pass it to the frontend (perhaps via query parameter or a global variable in the page) to trigger the initial view. A simpler approach is: if `--policy-id` is given, we perform the initial computation and perhaps store that result so that when the UI first calls `/api/graph` (with no ID), we return the default. If no policy is given, the UI on startup might prompt the user to pick one, or default to the first available policy.

* **Full Model (All Policies)**: In this initial design, we emphasize single-policy mode because that’s where showing actual values makes sense (one number or vector per node). However, we could also allow `policy_id = "ALL"` or similar to represent the full dataset. In that case, computing the graph would involve running the model on all data (like `run_model`) and perhaps presenting node values as “(multiple values)” or aggregated statistics. This is complex and not a focus now, so we will likely not implement it initially. The “toy model all nodes” phrasing refers to showing all *nodes* (columns) in the graph, not all policies.

## React Flow Frontend: Graph Visualization

On the client side, the Next.js React application will handle rendering the graph and providing user controls:

* **React Flow for Rendering**: We will use React Flow (a popular library for drawing node-link diagrams in React) to display the computation graph. Each node from the JSON will be rendered as a box, and edges as connecting lines. React Flow supports features like zoom/pan, drag-to-rearrange, and interactive styling. By default, we may use a simple layout (React Flow will position nodes automatically if we supply no coordinates, but that often results in a messy layout). We can improve layout by computing positions for nodes (e.g., topological sorting the graph and then assigning (x,y) coordinates in layers). A simple approach for initial version: arrange nodes in a layered graph based on dependency depth (like source nodes at top, final outputs at bottom). We can do this in the frontend after fetching the graph JSON:

  * Determine nodes with no incoming edges (these are input or base nodes) and place them in the first row.
  * Place their dependents in the next row, and so on.
  * React Flow also has a “dagre” (directed acyclic graph layout) plugin that can auto-layout a DAG. We might use a layout algorithm to avoid manual coordinate calculation. The design will note this as an implementation detail that can be handled with existing libraries or a small utility.

* **Node Presentation**: Each node box will display the node’s label and perhaps a snippet of its value. For example, the box title could be the column name, and beneath it we show the value (for the selected policy). If the value is a vector, we might show “\[x, y, ...] (n=480)” or some brief summary. On hover or click, we can reveal more details (see below). Nodes might be color-coded or styled differently if they are input data vs calculated, or perhaps if they belong to different sections of the model (though we don’t necessarily have section info).

* **Edge Presentation**: Edges will visually connect dependencies to dependents. React Flow will handle drawing these. We might style them (solid lines, arrows) to indicate direction. Hovering on an edge might optionally highlight the two connected nodes.

* **Interactivity**: The UI will include controls to enhance understanding:

  * **Policy Selector**: A text box or dropdown to input a policy ID and request the graph for that policy. If the data set is small, we could populate a dropdown with all IDs. If large, a text input with a “Load” button might be used. When the user selects a new ID and submits, the frontend will call the `/api/graph?policy_id=X` endpoint, get the new JSON, and update the graph view dynamically (React state update).
  * **Node Details on Click**: Clicking a node could open a sidebar or tooltip with full details: the formula (with maybe syntax highlighting), the source file and line (and perhaps the code context), and the full set of sample values. For example, if a node is defined in `model.py:27`, the sidebar might show: “**Formula:** `premium_total = premiun * 12` (at model.py:27)” and “**Value:** premiun = 100, so premium\_total = 1200” (i.e., show substitution of actual values, if available). This is analogous to Excel’s “Evaluate Formula” step-by-step view, albeit simplified. We can get the needed info from the JSON (the node already contains formula, source, sample values). If the JSON doesn’t include substituted values, the frontend could derive a simple substitution: e.g., replace references in the formula string with the dependency nodes’ values. However, doing this robustly might be tricky if the formula is complex, so the initial version might just list the dependency values separately. (A future enhancement is to pre-compute a formatted “formula with values” string on the backend – see **Future Improvements**).
  * **Zoom/Pan**: React Flow by default enables panning and zooming the canvas, which will help navigate large graphs.
  * **Filtering/Scoping Controls**: Though the initial plan is to show all nodes, we anticipate adding UI controls to filter the graph. For example, a search box to highlight nodes by name, or a toggle to “show upstream of selected node only” (to focus on a particular chain of calculations). The backend is already prepared to send the full graph; filtering can be done client-side by hiding certain nodes/edges. We can mention this in the plan as a roadmap item.

* **Including Input Data Nodes**: The computation graph likely includes only calculated columns (set via `af[...] = ...` in the model code). However, if those formulas reference columns from the input data (e.g., `af["age"]` or `af["premium"]` which came from the model points file), those inputs should appear as source nodes in the graph so that dependencies are explicit. We have two ways to handle this:

  1. **Treat input columns as pre-existing nodes**: When building the node list, if a dependency name is not one of the computed operations, we assume it’s an original column. We can create a node for it with no formula (or formula could be “(input column)”), and perhaps mark its source as “model points file”. Its value for the selected policy can be taken from the input data row. For example, if `premiun` (typo of premium) is a field from input, create node `premiun` with value 100 and label it as input.
  2. **Alternatively**, we could pre-populate the ActuarialFrame’s graph with initial columns. The current implementation of ActuarialFrame’s tracing does not explicitly add input columns to `_computation_graph` (it starts empty and only captures new assignments). So it’s easier to handle at the JSON assembly stage as described in step 1. We will implement logic to add a node for each dependency that isn’t already listed as a node alias. This ensures the graph is complete and every edge references a defined node.

  Representing input nodes distinctly (maybe a different color or dashed border) can help users identify given data vs calculated results.

* **Handling Errors**: If a model computation fails for a given policy (e.g., due to an edge-case causing an exception), the backend would return an error response. The design should handle this gracefully. Initially, we can catch exceptions in the `/api/graph` handler: if an error occurs during `af.profile()`, we capture the error message and return a JSON with an `"error"` field instead of nodes. The UI can display the error (maybe in a popup or in place of the graph). Gaspatchio’s enhanced error messages (with context and suggestions) can be leveraged here – potentially showing the user exactly which formula failed. However, implementing error display is secondary; the primary focus is the graph when things succeed. We note this so that the design doesn’t preclude showing errors via the same interface, aligning with Gaspatchio’s emphasis on contextual error reporting.

## Triggering Recalculation for a Policy (Backend Workflow)

When the frontend requests a new policy’s graph (via `policy_id` param), the backend will:

1. **Receive Request**: FastAPI parses the query parameter `policy_id`. The `serve` CLI will likely have been started with known `model_path` and `data_path` (from the CLI args), and possibly an initial policy. These can be stored as global or within the FastAPI app state (e.g., using `app.state` or dependency injection).

2. **Validate Policy ID**: Convert the `policy_id` to the appropriate type (likely integer). The runner’s logic expects an int and even checks that the ID exists. We will do similar validation. If the policy is not found, we return a 404 or a JSON error indicating “Policy ID not found” along with maybe a preview of valid IDs (the runner provides a preview of available IDs which is helpful for user feedback).

3. **Filter Data**: Using the cached full dataset (Polars DataFrame or LazyFrame) filtered by the ID. If we have a Polars DataFrame in memory, we do something like `filtered = df.filter(pl.col(id_column) == policy_id_int)`. We expect exactly one row (assuming unique policy IDs). If the model points file has multiple entries per policy, then filtered could be multiple rows – but Gaspatchio might treat that as multiple records to iterate? In many actuarial models, each policy is one record, so we’ll assume one row for now. Either way, we can feed the filtered LazyFrame into ActuarialFrame.

4. **Construct ActuarialFrame**: `af = ActuarialFrame(filtered.lazy(), mode="debug")`. (We use lazy so that actual computation is deferred, aligning with how `run_single_policy` works with a lazy input.) We enable tracing by default in debug mode – the `ActuarialFrame` initializer will set up `_tracing=True` automatically for debug mode (or we may ensure it).

5. **Run Model Function**: Call the loaded model function with `af` as argument, or if the model is defined as `def main(af: ActuarialFrame): ...`, we call it directly. The runner uses `dsl_run_model(model_func, df)` which likely handles differences between model definitions; for simplicity, we can do the same call (`gaspatchio_core.run_model(model_func, af)`). This executes the model’s calculations in *tracing mode*. Thanks to the decorator/wrapping logic in Gaspatchio, when in debug mode all the assignments made inside the model function do **not** immediately modify `af._df`. Instead, each `af["new_col"] = expr` call triggers `ActuarialFrame.__setitem__`, which sees `_tracing=True` and thus calls `append_operation_to_graph` and skips actual execution. The model function, if written in a typical way, might end by returning the frame or nothing; either way, after it finishes, `af._computation_graph` now holds a list of all operations that were defined in that run (in order).

6. **Collect Results**: Call `result_df, profile_df = af.profile()`. The `profile()` method will take the `af._computation_graph` and apply each operation to the internal Polars LazyFrame, then execute `.profile()` to get the actual DataFrame result and a Polars profiling table. We get the `result_df` (Polars DataFrame) which contains the calculated columns for that one policy. The values we need for each node can be extracted from this `result_df` easily (for scalar columns, just take the 0th row’s value; for list columns, take the 0th row which is a list).

7. **Build JSON Response**: Iterate over `af._computation_graph` (which is a list of `TracedOperation`). For each operation:

   * Determine its dependencies: if we had augmented `TracedOperation` to store dependencies (future feature), we could use that. If not, we derive by scanning the expression string or using Polars metadata. We might implement a helper that for a given `pl.Expr`, finds all `pl.col(...)` references. Polars doesn’t yet have an official AST extract, but the string representation includes `col("name")` tokens. A simple regex on `str(operation.expression)` could extract `"name"` tokens. Also, since we have the final list of aliases, we can cross-check each alias to see which expressions include it. This approach is manageable for initial implementation. (We will be careful to filter out the alias itself, focusing on true dependencies.)
   * Fetch the computed value from `result_df`: using the alias as column name, get the value. If the value is a scalar (Polars `int64`, `float64`, etc.), use that directly (possibly cast to Python int/float for JSON). If it’s a list (Polars `List` type), get the Python list. For large lists, as noted, we will slice it for the sample. The issue description suggests not to overwhelm the UI with huge arrays, so we include just a summary.
   * Include source location and formula: from `operation.metadata` we have `file_name`, `line_number`, and even the exact `source_line` of code. We’ll include those. If needed, we can shorten the file path to just the base name for display (using `metadata.display_filename` which already prettifies Jupyter vs script).
   * Mark inputs: if an operation’s expression is simply `col("X")` or a literal (which might happen if the model explicitly sets a column to a constant or something), and it has no dependencies, it might be an input or base value. We might skip marking since it will just show formula as e.g. `= 5` or so. Real input columns won’t appear in `_computation_graph`, so those we add separately as described (from dependencies that are not in alias list).

   After assembling nodes, we create edge list as described.

8. **Return JSON**: Return the JSON to the client. FastAPI will automatically convert our Python dict to JSON. We should ensure values are JSON-serializable (Polars types need conversion to Python types, e.g. use `value.item()` for numpy scalar, or `.to_list()` for series).

This flow will be executed each time a new policy\_id is requested. Thanks to caching model and data, steps 4–8 are the main repeated work. Polars and Rust optimizations should make a single-policy run quite fast (especially in debug mode with minimal optimization; but note we are only processing one row, albeit with vector operations inside – which Polars will handle quickly). This satisfies the *“default fast”* principle: the user makes a change (selects a policy) and sees the result quickly with minimal overhead. The design avoids any heavy initialization on each interaction.

**Concurrency**: We don’t expect multiple concurrent users, but FastAPI can handle overlapping requests. If a user somehow triggers two requests at once (e.g., double-clicks or multiple policy fetches), we should be careful that they don’t interfere. Since each request uses a fresh ActuarialFrame and the model function is pure (no global mutable state in calculations ideally), it should be fine. Polars can run multi-threaded by default, but for a single row this is trivial. We likely won’t need locking, but it’s something to test.

## Architectural Alignment with Gaspatchio Principles

This feature is designed in line with Gaspatchio’s core architectural principles:

* **Meet Users Where They Are**: We integrate the tool into the existing CLI (`gspio`) so actuaries can invoke it in the same way they run models, rather than requiring new environments or complex setup. The UI is delivered through a local web page, which is a familiar medium, and it visualizes formulas in a spreadsheet-like dependency graph – resonating with actuaries’ Excel experience. This supports the “ergonomics that feels Python but reads like a spreadsheet” ethos. We respect existing model code and data formats (no need to convert anything; you point the command at your Python model and data file, just like `run-model`).

* **Design for AI Assistance**: By exposing the computation graph in a structured JSON, we’re effectively making the model’s logic machine-readable. This aligns with Gaspatchio’s *LLM-native* direction. In the future, an AI tool could ingest the JSON to explain the model, verify it, or even suggest changes. Also, because we include rich metadata (source code lines, etc.), this output could feed into an AI “agent” that helps debug models. We are essentially providing *“LLM-friendly structured output”* (as noted in the architecture docs for error handling) to assist automation.

* **Default Fast, Interactive Feedback Loop**: The serve command is aimed at the rapid development cycle – change a model, run the server, and interactively see results for different inputs in real-time. We emphasize quick turnaround (no long compilation steps). For instance, there’s no JIT warmup; selecting a new policy triggers an immediate computation using Polars with negligible overhead, so actuaries can quickly iterate through scenarios. By keeping computations local and in-memory, and leveraging Polars’ efficiency, we ensure a snappy UI that encourages exploration, which is crucial for the change→test→refine loop.

* **Reusing Core Components**: The design respects the separation of concerns in Gaspatchio’s architecture – we reuse the *Python binding* layer and Rust core via the ActuarialFrame and do not reimplement any business logic. The serve tool lives in the Python interface layer (no changes to the Rust core). It simply adds a new interface on top of what’s already provided. This keeps the core pure and leverages the proven calculations and tracing there.

* **Debug Mode and Tracing**: We intentionally run in debug mode to use the enhanced tracing capabilities that Gaspatchio provides. This mode is designed to capture the kind of info we need (computation graph with context) and is meant for model understanding over raw performance. The serve tool can be seen as an extension of Gaspatchio’s debug tooling – akin to a visual debugger for model formulas. We maintain the dual-mode philosophy: the user can still run `run-model` in optimize mode for speed, but use `serve` (debug mode) for introspection. Both modes use the same engine underneath, so there’s consistency in results.

* **Excel Compatibility & Tracing**: One of the reasons Excel remains popular is the ease of tracing formulas. Our tool brings a similar capability to Gaspatchio, reinforcing the *Excel function compatibility* goal not just in function support but in user experience. We also contribute to the *enhanced debugging and tracing* aspect by providing a new way to inspect calculations step-by-step.

In summary, `gspio serve` extends Gaspatchio in a way that **improves transparency and trust** in the model outputs, without deviating from the framework’s architecture. It layers a user-friendly UI on top of the robust core, demonstrating the flexibility of Gaspatchio’s design.

## Technical Decisions and Trade-offs

This section discusses **key technical choices**, along with alternatives considered:

* **Choice of Web Framework (FastAPI)**: We chose FastAPI for the backend because it integrates well with Python and has simple support for static files and JSON APIs. An alternative was to use a simpler built-in server (like Python’s http.server or the wsgiref as spaCy did). However, FastAPI (built on Starlette) gives us more flexibility for future expansion (e.g., adding auth, more complex API logic) and is a familiar tool in modern Python web development. It also allows using Pydantic for data models if we wanted to formalize the request/response schema (though for now, a simple dict is enough). The performance overhead is minimal for our use case, and using Uvicorn means we get production-grade serving if needed. The trade-off is an extra dependency (FastAPI & Uvicorn), but these can be added to an optional extras (e.g., `pip install gaspatchio-core[ui]`) if we don’t want them always installed. Given they are fairly standard, it’s acceptable to include them by default for this feature’s convenience.

* **Frontend Technology (Next.js & React)**: We decided on a React-based SPA (with Next.js for ease of setup) to implement a rich interactive UI. Alternatives:

  * Use a pure static HTML + JavaScript (no framework) to visualize the graph. We could have, for example, used D3.js or even Mermaid.js to render a graph. That might have been simpler to bundle (just an HTML file with a `<script>` can be served without a build step). But building an interactive interface (with filtering, clicks, etc.) from scratch is time-consuming. React Flow provides ready-made components for graphs (dragging, zooming, etc.), accelerating development.
  * Use a Python dashboarding library like Streamlit or Plotly Dash. While these can create interactive apps, they would add heavy dependencies and not integrate as cleanly with our CLI workflow. Streamlit, for example, runs its own server and has its own UI idioms, which are less customizable for our graph needs. We opted for the flexibility of a custom React app.
  * Use Jupyter notebooks (since Gaspatchio is aiming for LLM integration, one could imagine a Jupyter widget for the graph). However, that would require the user to be in a Jupyter environment, which is not always the case for actuaries running CLI tools.

  The trade-off with Next.js/React is the build process complexity and requiring Node for development. In our team, this is acceptable as we likely have front-end expertise. Next.js is perhaps overkill if we don’t use its SSR capabilities – we mainly need a static SPA. We could use Create React App or Vite as well. We chose Next.js because it’s a well-supported framework, and if in the future we wanted some server-side rendering or incremental static generation for parts of the app, it’s available. For now, we will treat it as a static app.

* **React Flow vs. Custom Graph Viz**: React Flow was chosen for its feature-rich graph visualization. Another alternative was using an existing graph visualization format, e.g., generating a Graphviz DOT file or using a library like D3 to render SVG. Graphviz could produce a nice static image or SVG of the computation graph which we could display, but it would not be interactive. Given the importance of interactivity (tooltips, clicking nodes, etc.), React Flow was the better choice. A possible alternative could be libraries like Cytoscape.js or D3-force, but React Flow’s integration with React and out-of-the-box controls made it a strong candidate. The trade-off is we lock into its way of doing things (for example, custom layout might need extra work, and styling might be a bit opinionated), but those are manageable.

* **Policy-by-policy computation vs. full dataset**: A significant decision was to compute the graph for one policy at a time on demand, rather than computing everything upfront. We considered:

  * Running the model for all policies once (like `run-model`) and then simply allowing the UI to pick a row from the results to display values. This would mean only one expensive computation at startup, and very fast switching of policies (just plucking values from an in-memory DataFrame). However, for very large data, running the full model could be slow or use a lot of memory, and the user might only be interested in a handful of policies. Also, capturing the computation graph in a single run for all policies is still essentially the same as for one (the graph of formulas doesn’t change with multiple rows; it just doesn’t have particular values per policy). We would still need to extract values for whichever policy is selected. We realized we’d need to map values to the graph on a per-policy basis anyway, which complicates a single-run approach (we’d have to store *every node’s values for every policy*, which is basically the entire result table – possibly huge).
  * Thus, we opted for on-demand single-policy runs. This is more efficient if the user only examines a few cases, and it naturally provides the exact values for that case. The cost is that each selection triggers a computation. But since Polars is fast and a single row projection is not heavy, this cost is low. It also avoids storing the entire result dataset in memory on the Python side (though Polars LazyFrame might be holding data, depending on execution mode).
  * We might later optimize by keeping the `result_df` of the last run and if the user selects a policy nearby or re-selects, perhaps reuse some data, but that’s premature. Given debug mode is not highly optimized (it might not cache previous runs), it’s fine to rerun. Each run is independent.

* **Extending `TracedOperation` vs. deriving data**: Currently, `TracedOperation` does not include the dependency list or values (the issue #50 proposes adding these). We have to derive dependencies and attach values ourselves in the design. We could consider modifying Gaspatchio’s code to collect dependencies during tracing (e.g., when an operation is appended, inspect the expression). We decided not to rely on an immediate core change; instead, handle it in the serve logic for now. The design, however, remains future-proof: if Gaspatchio adds `dependencies` and `sample_values` to `TracedOperation` (which seems planned), we will use those directly. This separation keeps the serve feature from being blocked by core changes, but we stay aligned so that we can seamlessly upgrade once the core provides richer trace data.

* **Security**: Since this tool is for local debugging, we are not implementing authentication or permission checks. The server will be openly accessible on the given host/port. By default using localhost mitigates most risks. If needed, we could allow a flag like `--host 0.0.0.0` to let the user explicitly expose it (some might want to view the UI from a different machine, etc.). We note that when binding to `0.0.0.0`, it’s effectively open to anyone on the network, so a caution would be documented. We won’t implement any user login or similar for now, as it’s out of scope (development tool assumption).

* **Memory and Persistence**: The server runs in-memory and does not persist any results (aside from what’s already on disk in the model points file). This is fine for our use case. If the user wants to save a particular graph view, they could screenshot or perhaps we can implement an “Export graph as JSON/PNG” feature later. It’s not a current requirement.

* **Alternate Output Formats**: We considered if the CLI should also support outputting the graph JSON to a file (for users who may want to use it outside the UI). For example, `gspio serve --policy-id 123 --output-graph-json graph.json` could just dump the JSON without running a server. This could be useful for automated analysis or if someone wants to plug it into another tool. We decided that’s a nice-to-have but secondary; the primary goal is the interactive experience. The internal implementation will in fact generate that JSON, so adding an option to save it would be trivial. We might note this as a possible extension.

## Related Systems and Prior Art

It’s useful to compare this design to a few related systems for context:

* **Excel Formula Auditing**: Excel allows users to trace precedents and dependents of a cell, and even evaluate a formula step by step. Our graph is essentially a more comprehensive view of what Excel’s “formula auditing arrows” do – showing all relationships at once, with the added benefit of seeing actual values. This is directly motivating our feature. We bring the transparency of Excel to a more powerful actuarial modeling environment.

* **spaCy’s displaCy**: As noted, spaCy’s `displacy.serve` spins up a local web server to visualize NLP dependency graphs. That served as proof that users appreciate quick visualization tools. Our approach differs in that our content is dynamic (changing with user input) and we use a full web app stack for richer interaction.

* **Dask Distributed’s Task Graph**: Dask (a Python library for parallel computing) has a web dashboard that shows a graph of tasks and their dependencies. It updates as tasks progress. While our use-case is different, the concept of visualizing computational dependencies at runtime is similar. Dask’s graph is more performance-oriented (showing which tasks are running), whereas ours is for formula logic. We mention it to highlight that graph UIs can greatly aid understanding complex computations.

* **TensorBoard and Neural Network Graphs**: In machine learning, tools like TensorBoard show computational graphs of neural networks. Again, different domain, but they address the challenge of clarity in complex computation. One takeaway is to ensure our nodes have clear labels and grouping; neural net graphs often allow collapsing subgraphs. In actuarial models, we might consider grouping nodes by sections (for instance, all mortality-related calculations could be one group). This is a potential future enhancement (not in initial scope, but worth noting as analogous to how TensorBoard lets you group nodes).

* **Python Debuggers**: Traditional debuggers let you inspect values but not the whole formula graph at once. Gaspatchio’s debug mode plus this UI essentially creates a new form of debugger focused on data flow. This is fairly novel in actuarial tools, bridging a gap between code and the Excel way of thinking.

These analogies reinforce that our design is on a good path: it uses proven ideas (graph visualization for computations) in the context of Gaspatchio’s unique combination of spreadsheet-like formulas and code.

## Future Improvements and Visual Tooling (Appendix)

While the initial implementation will meet the core requirements, we envision many enhancements that can build on this foundation:

* **Richer Node Interactions**: We can allow users to click a node and *isolate* the subgraph of that node. For example, clicking on a particular result column could highlight all its precedent nodes (everything that feeds into it) and grey out unrelated parts. This is akin to selecting a cell in Excel and seeing direct precedents, but we could extend it to all ancestors. Conversely, we could highlight dependents (what downstream calculations a given node influences).
* **Step-by-Step Formula Evaluation**: An advanced feature (inspired by Excel’s “Evaluate Formula”) would let the user pick a node and step through the calculation substituting values one layer at a time. We already capture the needed data (each node’s value and its dependencies’ values). We could implement a mode where the node’s formula is displayed, and each click replaces a reference with the actual number (like the example in the issue – showing how a mortality rate formula evaluates through intermediate arithmetic). This would be especially helpful for debugging complex formulas involving multiple operations.
* **Time Series Visualization**: If a node’s value is a vector (e.g. cashflows over time), it might be useful to visualize that series. We could integrate a small sparkline chart or allow the user to expand a node to see a graph of the values over time. Alternatively, the user could select a time index and have the graph update to that slice (though Gaspatchio’s computations are not easily sliced by time since each formula might combine entire vectors).
* **Filtering and Search**: For large models, a search bar that highlights nodes matching a name or formula text would be handy. E.g., typing “prem” could filter to show only nodes with “premium” in the name or formula. We could also implement checkboxes to hide certain categories of nodes (if we can categorize by type or naming convention).
* **Grouping and Collapsing**: Possibly group nodes by a certain attribute. If the model code is structured (for example, maybe different sections or functions), we might feed that info into the graph (perhaps by naming conventions or by manually marking sections in code). The UI could then let you collapse a whole group to simplify the view.
* **Live Reload on Code Change**: In a future iteration, we could watch the model file for changes and auto-reload the graph. Akin to how front-end tools reload on save, if an actuary edits the model Python code, the server could detect it (via file timestamps) and re-import the model, perhaps even auto-recomputing the graph for the currently selected policy. This would tighten the development loop further. This requires careful handling of Python module reloading.
* **Integration with Error Handling**: If a model run fails for a selected policy (say a `ZeroDivisionError` in a formula), we could visualize a *partial graph* up to the point of failure and mark the failing node in red. The error message could be displayed on that node. Because Gaspatchio’s debug mode now captures error context, including the failing operation and suggestions, we could surface that in the UI to guide the user to the fix. This turns the graph into not just a viewer but a debugging assistant.
* **Performance Profiling Overlay**: Using the `profile_info` we get from Polars, we could show how long each operation took or some indicator of heavy computations. E.g., color an edge or node border based on fraction of total run time. This would help in optimizing models (though in debug mode, performance isn’t the main goal, it might still be informative).
* **AI Assistant Hooks**: As Gaspatchio is “AI-ready”, we could imagine an AI agent that reads the graph and answers questions (“Why is premium\_total 0 for policy 123?”) or even suggests new formulas. While not in scope for now, having the structured graph output is the first step to enabling such features down the road.

All the above ideas can be built incrementally on top of the system we are designing. By focusing now on delivering the core **system output** – the JSON graph with formulas, metadata, and values – we lay the groundwork for these visual and intelligent enhancements. The current design ensures that the backend produces a comprehensive representation of the model’s logic and execution for a given input. With that foundation, the frontend (or other consumers of the JSON) can evolve dramatically without requiring fundamental changes to how the data is gathered.

In conclusion, `gspio serve` will provide an immediate, practical benefit for model developers by visualizing the otherwise invisible calculation graph. It leverages Gaspatchio’s strengths (Python-native modeling, Polars performance, debug tracing) and extends the framework’s usability in the model debugging phase. This design carefully balances new functionality with alignment to existing architecture and principles, ensuring that the feature feels like a natural extension of Gaspatchio’s toolkit. The interactive graph viewer will make complex actuarial models more transparent and easier to validate, compare, and explain – fulfilling a critical need in actuarial workflow that up to now has often been served by ad-hoc Excel checks. Gaspatchio, with this addition, moves a step closer to being a modern replacement for those legacy workflows, combining high performance with high explainability.

**Sources:**

* Gaspatchio Architecture Summary – ActuarialFrame and computation graph
* Gaspatchio CLI and Runner – usage of debug mode and single-policy filtering
* Gaspatchio Tracing Code – capturing operations with source metadata
* Gaspatchio Issue #50 – proposal for values in computation graph (Excel-style trace)
* spaCy displacy serving method – simple local web server for visualizations
* Gaspatchio Principles (README) – Meeting users where they are, AI readiness, speed of iteration
