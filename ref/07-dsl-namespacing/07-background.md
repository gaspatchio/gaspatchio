# Background: Namespacing for ActuarialFrame DSL

## Context

The Gaspatchio project utilizes a custom Domain Specific Language (DSL) centered around the `ActuarialFrame` class. This class acts as a wrapper around Polars DataFrames/LazyFrames, providing a convenient interface for actuarial modeling tasks while potentially enabling tracing, custom optimizations, and specific actuarial functions.

Currently, domain-specific helper functions, such as `date_from_excel_serial` (converting Excel serial dates) and `create_projection_timeline` (generating actuarial projection dates), are implemented as standalone functions within utility modules (e.g., `gaspatchio_core.dates`). While functional, this approach presents challenges as the DSL and the number of helper functions grow.

## Problem Statement

As more actuarial-specific functions are added (e.g., for financial calculations, statistical analysis, specific reserving methods), implementing them as standalone functions leads to:

1.  **Namespace Pollution:** The global or module namespace becomes cluttered, making it harder to manage and understand the available functionality.
2.  **Discoverability Issues:** Users (including human developers and AI assistants) may find it difficult to discover relevant functions. Standard IDE autocompletion on an `ActuarialFrame` object (`af.`) or a column proxy (`af["col"].`) won't reveal these standalone utility functions.
3.  **Inconsistent API Feel:** The pattern deviates from common practices in data manipulation libraries like Polars, which use accessor namespaces (e.g., `df['col'].dt.year()`, `df['col'].str.contains(...)`) for domain-specific operations. This makes the `ActuarialFrame` DSL feel less intuitive for users familiar with such libraries.
4.  **Scalability Concerns:** Adding new domains (e.g., finance, mortality) would further exacerbate namespace clutter if functions remain standalone.

## Goal

The goal is to design and implement a robust namespacing strategy for the `ActuarialFrame` DSL. This strategy should:

1.  **Improve Organization:** Logically group related functions (e.g., all date-related functions together).
2.  **Enhance Discoverability:** Allow users and tools (IDEs, LLMs) to easily find available operations through standard attribute access (e.g., `af.date.<method>`, `af['col'].date.<method>`).
3.  **Create a Clean API Surface:** Define a clear, intuitive, and consistent interface for interacting with `ActuarialFrame` and its columns/expressions.
4.  **Promote Scalability:** Provide a structure that can easily accommodate new functional domains in the future.
5.  **Facilitate Tooling:** Explicitly support IDE autocompletion and provide a well-defined structure that can be easily represented in context files (e.g., `llms.txt`) for AI code generation assistants.
6.  **Resonate with Actuaries and LLMs:** The structure and naming conventions should feel intuitive and familiar to actuaries (potentially drawing parallels to common actuarial terminology or Excel concepts where appropriate, without being un-Pythonic), while also being explicit and predictable for LLMs performing self-discovery and code generation. The ultimate aim is to enable LLMs to produce code using this DSL that an experienced actuary would be delighted to have written themselves.

## Potential Approaches & Considerations

Several namespacing approaches could be considered:

1.  **Single Custom Namespace:** Introduce a single top-level namespace (e.g., `af.gs.<method>`, `af['col'].gs.<method>`).
    *   *Pro:* Simple to implement initially.
    *   *Con:* May become cluttered itself as many different types of functions are added.
2.  **Domain-Specific Nested Namespaces:** Introduce multiple namespaces based on functionality (e.g., `af.date.<method>`, `af['col'].date.<method>`, `af.finance.<method>`, `af['col'].finance.<method>`).
    *   *Pro:* Highly organized, scalable, aligns well with Polars pattern.
    *   *Con:* Slightly more complex implementation (requires multiple namespace classes).
3.  **Frame vs. Expression Distinction:** Namespaces need to exist at both the `ActuarialFrame` level (for operations acting on the whole frame, like `create_timeline`) and the `ExpressionProxy`/`ColumnProxy` level (for operations acting on a single column/expression, like `from_excel_serial`). The design must clearly handle this distinction.
4.  **API Design:** Should methods modify the frame/expression in place or return new instances (promoting immutability)? Immutability is often preferred but requires users to reassign results (`af = af.date.create_timeline(...)`).
5.  **Integration with Polars Namespaces:** How should custom namespaces interact or coexist with standard Polars namespaces (`.dt`, `.str`, etc.)? They should likely be distinct siblings.
6.  **Naming Conventions:** How can method and namespace names best balance Python best practices, discoverability for LLMs, and familiarity for actuaries transitioning from other tools (like Excel)? For example, should a function converting Excel dates be `.date.from_excel_serial()` (descriptive) or perhaps something shorter if a common actuarial term exists?

## Research Task

Investigate best practices for implementing accessor namespaces in Python libraries, particularly in the context of DSLs wrapping other libraries (like Polars). Key areas for research include:

1.  **Polars Implementation:** How does Polars implement its `.dt`, `.str`, `.list`, etc., accessors internally? What patterns can be adopted?
2.  **Other DSLs/Libraries:** How do other numerical/data manipulation libraries (e.g., Pandas, xarray, potentially actuarial libraries if examples exist) handle namespacing for domain-specific operations?
3.  **API Design Patterns:** Explore patterns for designing the namespace classes and methods, considering usability, performance, and immutability trade-offs.
4.  **Tooling Integration:** How can the chosen namespacing structure, combined with Python type hints and `.pyi` stub files, best support IDE autocompletion and provide optimal context for Large Language Models (LLMs) performing code generation tasks with the `ActuarialFrame` DSL? Identify how to best represent this API surface for programmatic consumption.

The findings should inform the final design decision for namespacing within the `ActuarialFrame` DSL, prioritizing clarity, usability, scalability, and seamless integration with development tools.
