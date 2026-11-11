---
category: language_standard
language: python
title: Python coding standards (PEP 8 / PEP 20 / PEP 257 essentials)
---
# Naming
Use snake_case for functions, methods and variables, CapWords for classes, UPPER_SNAKE_CASE for constants. Avoid single-letter names except for short loop indices. Names should reveal intent (`remaining_attempts`, not `x2`).

# Layout and readability
Limit lines to about 88-100 characters. Use four-space indentation. Group imports: standard library, third party, local. Do not use wildcard imports. Prefer early returns (guard clauses) over deep nesting.

# Functions
Keep functions short and single-purpose (rule of thumb: under 40 lines, under 5 parameters). Write docstrings for public functions describing arguments, return value and raised exceptions (PEP 257). Prefer type hints on public interfaces.

# Mutable defaults
Never use a mutable object as a default argument (`def f(x, items=[])`). The default is evaluated once at definition time and shared across calls. Use `None` and create the object inside the function.

# Comparisons
Compare to None with `is None` / `is not None`. Use `==` for value equality, never `is` for numbers or strings. Do not compare booleans with `== True`. Use `isinstance` rather than comparing `type(x)`.

# Exceptions
Catch specific exceptions. A bare `except:` also catches KeyboardInterrupt and SystemExit. Never silently `pass` inside an except block without a comment explaining why. Use `raise ... from err` to preserve causes. Use context managers (`with open(...)`) so resources are always released.

# Idioms
Use `enumerate` instead of `range(len(x))`, `zip` for parallel iteration, comprehensions for simple transforms, `dict.get` / `setdefault` / `collections.defaultdict` for counting and grouping, `str.join` for building strings in loops, `pathlib` for paths.
