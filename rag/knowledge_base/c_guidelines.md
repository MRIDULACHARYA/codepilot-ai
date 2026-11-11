---
category: language_standard
language: c
title: C programming guidelines
---
# Memory safety
Every `malloc` must be checked for NULL and matched by exactly one `free`. Set pointers to NULL after freeing. Never use a pointer after free or return the address of a local variable. Initialise all variables before use.

# Buffers and strings
Never use `gets`. Replace `strcpy`, `strcat` and `sprintf` with bounded versions (`snprintf`, `strncat`) and always reserve space for the terminating NUL. Validate array indices against the array length; off-by-one errors in `<=` loop bounds are a classic overflow cause.

# Integers
Beware signed overflow (undefined behaviour), signed/unsigned comparison, and implicit narrowing. Use `size_t` for sizes and indices. Check multiplication before allocating (`n * sizeof(T)` can overflow).

# Style
Use clear names, one declaration per line, braces on every if/for/while body, and `const` for read-only parameters. Compile with `-Wall -Wextra` and treat warnings as errors. Use tools such as valgrind or AddressSanitizer in testing.
