---
category: debugging
language: any
title: Common debugging patterns
---
# Off-by-one and boundaries
Check loop bounds (`<` vs `<=`), slice ends, and midpoints in binary search (`low <= high` loops with `mid + 1` / `mid - 1` updates). Test with empty input, a single element, two elements, and the first and last positions.

# Wrong conditions
Look for inverted comparisons, `and`/`or` mix-ups, missing parentheses around mixed boolean operators, and comparing the wrong variables. Truth-table the condition for the boundary values.

# None / null handling
Functions that may return None (dict.get, re.match, find) must be checked before use. Beware of treating falsy values (0, "", []) as missing; use `is None` when the distinction matters.

# State and aliasing
Mutable default arguments, shared references (`[[0]*n]*m` creates aliased rows), and mutating a list while iterating over it cause surprising behaviour. Copy before mutating when the caller does not expect changes.

# Infinite loops
Verify that every `while` loop makes progress toward its exit condition on every path, including `continue` branches that skip the update step.

# Integer and float arithmetic
Integer division (`//`) versus true division (`/`), rounding, float equality comparisons (use `math.isclose`), and division by zero on empty collections (average of an empty list).

# Debugging method
Reproduce first, minimise the input, state the expected result, then bisect: add assertions or print intermediate values to find the first point where reality diverges from expectation.
