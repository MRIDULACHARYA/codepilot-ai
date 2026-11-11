---
category: language_standard
language: java
title: Java coding conventions
---
# Naming
Classes use UpperCamelCase, methods and variables lowerCamelCase, constants UPPER_SNAKE_CASE, packages all lowercase. One top-level public class per file, named after the file.

# Structure
Keep methods short with a single responsibility. Prefer composition over inheritance. Make fields private and expose behaviour, not state. Prefer immutable objects and `final` where possible.

# Null handling
Avoid returning null for collections; return empty collections. Use `Optional<T>` for return values that may be absent. Check arguments with `Objects.requireNonNull`. Compare strings with `equals`, never `==`; put the literal first (`"x".equals(s)`) to avoid NullPointerException.

# Exceptions
Do not catch `Exception` or `Throwable` broadly and never leave a catch block empty. Use try-with-resources for anything implementing AutoCloseable. Prefer unchecked exceptions for programming errors and checked exceptions for recoverable conditions.

# Collections and equality
Override `hashCode` whenever you override `equals`. Use generics; avoid raw types. Beware of `ConcurrentModificationException` when removing from a list while iterating; use an Iterator or `removeIf`.
