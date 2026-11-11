---
category: data_structures
language: any
title: Data structure reference
---
# Lists / arrays
O(1) index access and amortised O(1) append; O(n) insert/delete in the middle and O(n) membership tests. In Python, `list.pop(0)` is O(n); use `collections.deque` for queues.

# Dictionaries and sets
Hash tables give average O(1) lookup, insert and delete. Keys must be hashable (immutable). Use sets for membership tests and de-duplication instead of scanning lists. Iteration order in Python dicts is insertion order.

# Stacks and queues
A stack is LIFO (list append/pop). A queue is FIFO (`collections.deque`, `queue.Queue`). Use `heapq` for priority queues (min-heap, O(log n) push/pop).

# Trees and graphs
Binary search trees offer O(log n) operations only when balanced. Graph traversal: BFS with a queue finds shortest paths in unweighted graphs; DFS with recursion or a stack explores deeply. Track visited nodes to avoid infinite loops on cycles.

# Strings
Strings are immutable in Python and Java; repeated `+=` in a loop is quadratic in the worst case. Use `join` or a `StringBuilder`.

# Choosing
Need ordering? sorted list / heap / tree. Need fast lookup? dict/set. Need FIFO? deque. Need counting? `collections.Counter`.
