---
category: runtime_errors
language: any
title: Common runtime errors
---
# Python exceptions
IndexError: index outside the sequence (often `range(len(x)+1)` or `x[i+1]` on the last element). KeyError: missing dict key; use `.get` or `in`. TypeError: wrong operand type or calling None. ValueError: right type, wrong value (e.g. `int("abc")`). ZeroDivisionError: dividing by zero or by `len([])`. AttributeError: attribute on None (a function returned None). RecursionError: missing or unreachable base case. StopIteration, UnboundLocalError, and FileNotFoundError are other frequent ones.

# Defensive checks
Validate input types and ranges at function boundaries. Handle empty collections explicitly. Guard divisions. Use `with` for files. Raise clear exceptions with messages instead of returning ambiguous sentinel values.

# Java/C equivalents
Java: NullPointerException, ArrayIndexOutOfBoundsException, ClassCastException, ConcurrentModificationException, NumberFormatException. C: segmentation fault from NULL or dangling pointers, buffer overflow, use-after-free, double free, memory leaks.

# Resource exhaustion
Unbounded recursion, infinite loops and unbounded memory growth cause hangs and crashes. Add explicit limits and timeouts.
