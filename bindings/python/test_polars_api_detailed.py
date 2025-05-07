import inspect

import polars as pl

# Create a simple expression
expr = pl.col("x")
print(f"Polars version: {pl.__version__}")

# Get direct access to methods
print("\nInspecting the Expr.map_elements method:")
print(f"Method type: {type(expr.map_elements)}")
print(f"Method __call__ signature: {inspect.signature(expr.map_elements.__call__)}")

# Try to call it directly
try:
    print("\nTrying direct method call with signature:")
    print("expr.map_elements.__call__(lambda x: x*2)")
    func = lambda x: x * 2
    expr.map_elements.__call__(func)
    print("✅ Success!")
except Exception as e:
    print(f"❌ Error: {e}")

# Try using a partial/bound method approach
try:
    print("\nTrying bound method with signature:")
    print("expr.map_elements(lambda x: x*2)")
    result = expr.map_elements(lambda x: x * 2)
    print(f"✅ Success! Result: {type(result)}")
except Exception as e:
    print(f"❌ Error: {e}")

# Try the named parameter
try:
    print("\nTrying bound method with named parameter:")
    print("expr.map_elements(function=lambda x: x*2)")
    result = expr.map_elements(function=lambda x: x * 2)
    print(f"✅ Success! Result: {type(result)}")
except Exception as e:
    print(f"❌ Error: {e}")

# Use an instance of the method class
try:
    print("\nTrying to create a new instance of the method:")
    method_class = expr.map_elements.__class__
    print(f"Method class: {method_class}")
    print(f"Method class signature: {inspect.signature(method_class)}")

    # Create a new instance and call it
    method_instance = method_class(expr, lambda x: x * 2)
    print(f"Created instance: {method_instance}")
    result = method_instance()
    print(f"✅ Success! Result: {type(result)}")
except Exception as e:
    print(f"❌ Error: {e}")

# Get to the underlying method implementation
print("\nLooking at other attributes:")
print(f"Method __self__: {getattr(expr.map_elements, '__self__', 'Not found')}")
print(f"Method __func__: {getattr(expr.map_elements, '__func__', 'Not found')}")

# Look at the class structure
print("\nClass hierarchy:")
cls = expr.__class__
while cls:
    print(f"- {cls.__name__}")
    cls = cls.__base__

# Try map_batches
print("\nTrying map_batches:")
try:
    result = expr.map_batches(lambda s: s * 2)
    print(f"✅ Success! Result: {type(result)}")
except Exception as e:
    print(f"❌ Error: {e}")

# Show the available wrapped functions
print("\nWrapped functions:")
wrapped_funcs = [
    name
    for name in dir(expr)
    if not name.startswith("_") and callable(getattr(expr, name))
]
for name in sorted(wrapped_funcs[:20]):  # Show first 20 only
    print(f"- {name}")
