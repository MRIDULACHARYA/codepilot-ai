---
category: testing
language: any
title: Testing best practices
---
# Structure
Each test checks one behaviour and has an explicit expected value. Name tests after the behaviour (`test_average_of_empty_list_raises`). Arrange-Act-Assert. Tests must be deterministic: no randomness, clock or network dependence.

# What to cover
Normal inputs, boundary values (empty, one element, minimum, maximum, just inside/outside limits), edge cases (duplicates, negative numbers, unicode), invalid inputs (wrong type, None) with the exception type asserted, and regression tests that reproduce a known bug.

# Pytest tips
Use plain `assert`. Use `pytest.raises(ExpectedError)` for failure paths and `pytest.mark.parametrize` for tables of cases. Use `pytest.approx` for floats. Keep fixtures small.

# Good expectations
Derive expected values from the specification or by hand, not by running the code under test and copying the output. A test that passes on both the buggy and the fixed code proves nothing about the bug.
