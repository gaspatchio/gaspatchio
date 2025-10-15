
<variables>
    $FUNCTION_NAME :str
    $GITHUB_URL :str
</variables>

<prompt>
Add $FUNCTION_NAME to @dispatch.py

add it to _NUMERIC_ELEMENTWISE

find the github polars reference at $GITHUB_URL

then write the function signature for $FUNCTION_NAME in @proxy.pyi
a good place to put it is in the order of the functions in _NUMERIC_ELEMENTWISE, find the last function in there and put our new function after it.


Use the guidelines in @recipes/write-docstring.md to write the docstring for $FUNCTION_NAME in @proxy.pyi

</prompt>


<testing>
run 
```bash
uv run gp-docstrings run-print-check --file gaspatchio_core/column/proxy.pyi --method "$CLASS_NAME.$FUNCTION_NAME"
```

eg for $FUNCTION_NAME = "clip" 
```bash
uv run gp-docstrings run-print-check --file gaspatchio_core/column/proxy.pyi --method "_BaseProxy.clip"
```

use this testing to ensure your docstring is correct, fix if not. 
</testing>