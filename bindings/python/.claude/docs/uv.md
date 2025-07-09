
## Using uv for package managment and running code in Yolo mode. 
This project will utilize @uv exclusively for packaging, building, and running Python code. This approach ensures a streamlined and efficient workflow.

Adding Dependencies with `uv add`
To add dependencies to your project, use the `uv add` command. This command updates your `pyproject.toml` and installs the specified packages into your project's environment. For example, to add the `requests` and `rich` packages:

```bash
$ uv add requests rich
```

This command will:
- Update the `dependencies` section in your `pyproject.toml`.
- Install the specified packages into your project's virtual environment.


### Running Scripts 
To execute scripts within your project's environment, use the `uv run` command. This ensures that the script runs with the project's dependencies properly configured. For instance, to run a script named `example.py`:

```bash
$ uv run example.py
```

#### Examples - Good
```bash
$ uv run --package gaspatchio-core jobs/basic/model.py main smol
```

This command will:
- Ensure the project's environment is up-to-date.
- Execute the specified script within that environment.

For more information, see the @Running Commands section in the uv documentation.

Running Tests with `uv run tests`
To execute tests within your project's environment, use the `uv run tests` command. This ensures that the tests run with the project's dependencies properly configured.

```bash
$ uv run tests
```

This command will:
- Ensure the project's environment is up-to-date.
- Execute the specified test script within that environment.


Project Initialization and Environment Management
To initialize a new project, use the `uv init` command:

```bash
$ uv init 
```
The `pyproject.toml` file contains your project's metadata and dependencies. The `.python-version` file specifies the Python version for the project. The `.venv` directory, which is created upon adding dependencies or running scripts, contains the isolated virtual environment for your project.


### Running Single-Command Typer Applications

When a Typer application defines only a single command using `@app.command()`, you do not need to specify the command name on the command line when using `uv run`. `uv run` will automatically execute that single command.

#### Examples - Good

Assuming `mix.py` contains a single Typer command named `run-model-code`:

```bash
# Correctly runs the single command without specifying its name
$ uv run mix.py path/to/model_code.py path/to/model_points.parquet --mode debug 
```

#### Examples - Bad (Unnecessary)

```bash
# While this might work, it's unnecessary for single-command apps
$ uv run mix.py run-model-code path/to/model_code.py path/to/model_points.parquet --mode debug
```


## References

- [uv docs](mdc:https:/docs.astral.sh/uv) @UV
- [Typer - One or multiple commands?](mdc:https:/typer.tiangolo.com/tutorial/commands/one-or-multiple)

