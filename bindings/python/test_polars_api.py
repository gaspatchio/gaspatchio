import polars as pl

# Create a simple DataFrame
df = pl.DataFrame({"x": [1, 2, 3, 4, 5]})


# Define a simple function
def square(x):
    return x * x


print("Testing map_elements...")
try:
    # Try with positional parameter
    result = df.with_columns(square_pos=pl.col("x").map_elements(square))
    print("Positional parameter succeeded:")
    print(result)
except Exception as e:
    print(f"Positional parameter failed: {e}")

try:
    # Try with named parameter
    result = df.with_columns(square_named=pl.col("x").map_elements(function=square))
    print("\nNamed parameter succeeded:")
    print(result)
except Exception as e:
    print(f"\nNamed parameter failed: {e}")


# Test map_batches
def batch_square(s):
    return s * s


print("\nTesting map_batches...")
try:
    # Try with positional parameter
    result = df.with_columns(batch_pos=pl.col("x").map_batches(batch_square))
    print("Positional parameter succeeded:")
    print(result)
except Exception as e:
    print(f"Positional parameter failed: {e}")

try:
    # Try with named parameter
    result = df.with_columns(batch_named=pl.col("x").map_batches(function=batch_square))
    print("\nNamed parameter succeeded:")
    print(result)
except Exception as e:
    print(f"\nNamed parameter failed: {e}")
