## Python Development Standards

### Code Style and Formatting
- All generated or edited code **must already be formatted**; assume `ruff format` (Black-compatible) will run in CI
- Ruff is configured with **`select = ["ALL"]`**, so code must lint clean except for ignores defined in `pyproject.toml`
- Use **f-strings** for all string interpolation
- Use **`pathlib.Path`** instead of `os.path`
- Prefer **`with`** context managers for resource handling
- Never use `print()` for production code – rely on the project's `loguru` logger
- Use lowercase with underscores for directories and files (e.g., `utils/data_processor.py`)

# Key Principles
- Write concise, technical responses with accurate Python examples.
- Use functional, declarative programming; prefer classes only for stateful components or when they provide clear organizational benefits.
- Prefer iteration and modularization over code duplication.
- Use descriptive variable names with auxiliary verbs (e.g., is_valid, has_data).
- Use lowercase with underscores for directories and files (e.g., utils/data_processor.py).
- Favor named exports for utility functions and preprocessing functions.
- Use the Receive an Object, Return an Object (RORO) pattern:
  - Functions should accept a single object parameter for complex inputs
  - Return a single object for complex outputs
  - Use Pydantic models for both input and output objects
  - Example:
    ```python
    @dataclass
    class ProcessConfig(BaseModel):
        input_path: Path
        batch_size: int = 100
        
    @dataclass
    class ProcessResult(BaseModel):
        processed_count: int
        errors: list[str]
        
    def process_data(config: ProcessConfig) -> ProcessResult:
        ...
    ```
- Use Typer for CLI applications with type hints and rich help text
- Use def for pure functions and async def for asynchronous operations.
- Use type hints for all function signatures
- Use Pydantic extensively:
  - Define models for all structured data
  - Use model validation for input sanitization
  - Use model_dump() for serialization
  - Use model_validate() for deserialization
  - Leverage Pydantic's built-in types (Path, HttpUrl, etc.)
  - Example:
    ```python
    class ChartConfig(BaseModel):
        output_dir: Path
        format: Literal["html", "png"]
        width: int = 800
        height: int = 400
    ```
- File structure: 
  - src/package_name/ for main package code
  - tests/ for test files
  - CLI entry points in root directory
- Use Polars for data manipulation and analysis
- Use Loguru for structured logging with rich formatting

### Error Handling and Validation
- Prioritize error handling and edge cases
- Handle errors and edge cases at the beginning of functions
- Use early returns for error conditions to avoid deeply nested if statements
- Place the happy path last in the function for improved readability
- Avoid unnecessary else statements; use the if-return pattern instead
- Use Loguru for structured logging with context
- Use Pydantic models to validate and parse complex inputs, reducing manual validation code

### Docstrings
- Ensure methods have the right docstrings
- Follow rules detailed in `gaspatchio-core/ref/12-docstring-and-examples/12-docstring-README.md`

### Key Dependencies
- Pydantic v2 for data validation and serialization
- Typer for CLI applications with type hints and rich help text
- Polars for data reading, manipulation and aggregation
- Loguru for structured logging
- Pydantic.AI for LLM interactions
- uv for packaging, building, and running Python
