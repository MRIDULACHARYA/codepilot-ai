---
category: complexity
language: any
title: Algorithmic complexity reference
---
# Big-O cheat sheet
O(1) constant: dict lookup, list index. O(log n): binary search, balanced tree, heap push. O(n): single pass, linear search. O(n log n): efficient sorting (Timsort, merge sort). O(n^2): nested loops over the same input, naive duplicate checks. O(2^n): naive recursive subsets or Fibonacci. O(n!): permutations.

# Spotting hidden cost
`x in some_list` inside a loop makes the loop O(n^2); convert the list to a set first. String concatenation in a loop, `list.insert(0, x)`, `list.pop(0)`, repeated `sorted()` calls inside loops and repeated slicing are common hidden linear costs. Recursion without memoisation may recompute subproblems exponentially; use `functools.lru_cache` or dynamic programming.

# Optimisation guidance
Choose a better algorithm or data structure before micro-optimising. Precompute values that do not change inside loops. Use generators for large streams to keep memory O(1). Measure with a profiler before and after; keep behaviour identical and confirm with tests.

# Space complexity
Account for recursion depth (stack space), copies created by slicing, and auxiliary structures. In-place algorithms use O(1) extra space.
