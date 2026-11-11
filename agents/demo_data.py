"""Deterministic DEMO samples.

Everything here is PREDEFINED and SIMULATED: it is not LLM output. The UI and the report label
it as such. If Docker is available the predefined tests are still *really* executed in the sandbox.
"""
from __future__ import annotations

SAMPLES: dict[str, dict] = {}


def _add(sid, title, description, code, issues, style_issues, corrected, changes, test_code, tests, explanation=""):
    SAMPLES[sid] = dict(
        id=sid, title=title, description=description, code=code.strip("\n") + "\n", issues=issues,
        style_issues=style_issues, corrected_code=(corrected.strip("\n") + "\n") if corrected else None,
        changes=changes, test_code=test_code.strip("\n") + "\n", tests=tests, explanation=explanation,
    )


_add(
    "binary_search", "Binary search skips the last candidate",
    "binary_search should return the index of target in a sorted list, or -1 if absent. Please find and fix any bugs.",
    '''
def binary_search(items, target):
    """Return the index of target in sorted items, or -1 if absent."""
    low, high = 0, len(items) - 1
    while low < high:
        mid = (low + high) // 2
        if items[mid] == target:
            return mid
        elif items[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
''',
    [dict(title="Incorrect loop boundary: last remaining candidate is never examined", severity="high", line_number=4,
          description="`while low < high` exits when one candidate is left, so a target at that position (e.g. a one-element list) is reported as missing.",
          suggested_fix="Use `while low <= high`.", confidence=0.95, category="bug")],
    [],
    '''
def binary_search(items, target):
    """Return the index of target in sorted items, or -1 if absent."""
    low, high = 0, len(items) - 1
    while low <= high:
        mid = (low + high) // 2
        if items[mid] == target:
            return mid
        elif items[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
''',
    [dict(description="Changed loop condition from `low < high` to `low <= high`",
          reason="The search window [low, high] is inclusive, so it is only empty when low > high.")],
    '''
from solution import binary_search


def test_single_element_found():
    assert binary_search([5], 5) == 0


def test_found_at_last_position():
    assert binary_search([1, 3, 5, 7], 7) == 3


def test_found_at_first_position():
    assert binary_search([1, 3, 5, 7], 1) == 0


def test_two_elements_second():
    assert binary_search([1, 3], 3) == 1


def test_missing_returns_minus_one():
    assert binary_search([1, 3, 5, 7], 4) == -1


def test_empty_list():
    assert binary_search([], 1) == -1
''',
    [dict(name="test_single_element_found", description="One-element list containing the target", category="boundary", expected="returns 0", covers=["BUG001"]),
     dict(name="test_found_at_last_position", description="Target is the last element", category="boundary", expected="returns 3", covers=["BUG001"]),
     dict(name="test_found_at_first_position", description="Target is the first element", category="normal", expected="returns 0", covers=[]),
     dict(name="test_two_elements_second", description="Two-element list, target second", category="boundary", expected="returns 1", covers=["BUG001"]),
     dict(name="test_missing_returns_minus_one", description="Absent target", category="normal", expected="returns -1", covers=[]),
     dict(name="test_empty_list", description="Empty input", category="edge", expected="returns -1", covers=[])],
    explanation="Binary search halves an inclusive window [low, high] each iteration; O(log n) time, O(1) space.",
)

_add(
    "average_empty", "Average of an empty list crashes",
    "average should return the arithmetic mean and raise ValueError for an empty sequence. Please debug it.",
    '''
def average(numbers):
    """Return the arithmetic mean of numbers."""
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
''',
    [dict(title="Division by zero on empty input", severity="high", line_number=6,
          description="`len(numbers)` is 0 for an empty sequence, raising an unhelpful ZeroDivisionError.",
          suggested_fix="Validate the input and raise ValueError with a clear message.", confidence=0.93, category="bug")],
    [],
    '''
def average(numbers):
    """Return the arithmetic mean of numbers.

    Raises ValueError if numbers is empty.
    """
    if len(numbers) == 0:
        raise ValueError("average() requires at least one number")
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
''',
    [dict(description="Added an explicit empty-input check raising ValueError", reason="Gives callers a clear, documented error instead of ZeroDivisionError.")],
    '''
import pytest

from solution import average


def test_average_of_integers():
    assert average([1, 2, 3]) == 2


def test_average_single_value():
    assert average([7]) == 7


def test_average_floats():
    assert average([0.5, 1.5]) == pytest.approx(1.0)


def test_average_negative_numbers():
    assert average([-2, 2]) == 0


def test_average_empty_raises_value_error():
    with pytest.raises(ValueError):
        average([])
''',
    [dict(name="test_average_of_integers", description="Mean of [1,2,3]", category="normal", expected="2", covers=[]),
     dict(name="test_average_single_value", description="Single element", category="boundary", expected="7", covers=[]),
     dict(name="test_average_floats", description="Float inputs", category="normal", expected="1.0", covers=[]),
     dict(name="test_average_negative_numbers", description="Negative values", category="edge", expected="0", covers=[]),
     dict(name="test_average_empty_raises_value_error", description="Empty list must raise ValueError", category="invalid", expected="ValueError", covers=["BUG001"])],
)

_add(
    "mutable_default", "Mutable default argument leaks state",
    "add_item appends an item to a list and returns it; each call without a list should start fresh. Find the bug.",
    '''
def add_item(item, items=[]):
    items.append(item)
    return items
''',
    [dict(title="Mutable default argument shared between calls", severity="medium", line_number=1,
          description="The default list is created once; items from earlier calls remain in later calls.",
          suggested_fix="Default to None and create a new list inside the function.", confidence=0.97, category="bug")],
    [dict(title="Missing docstring", severity="low", line_number=1, description="Public function has no docstring.",
          suggested_fix="Document arguments and return value.", confidence=0.6, category="style")],
    '''
def add_item(item, items=None):
    """Append item to items (or to a new list) and return the list."""
    if items is None:
        items = []
    items.append(item)
    return items
''',
    [dict(description="Replaced `items=[]` with `items=None` and create the list inside the function",
          reason="Avoids state shared across calls while keeping the same call signature."),
     dict(description="Added a docstring", reason="Documents behaviour.")],
    '''
from solution import add_item


def test_fresh_list_each_call():
    assert add_item(1) == [1]
    assert add_item(2) == [2]


def test_appends_to_given_list():
    existing = [1]
    result = add_item(2, existing)
    assert result == [1, 2]
    assert result is existing
''',
    [dict(name="test_fresh_list_each_call", description="Two calls without a list must not share state", category="regression", expected="[1] then [2]", covers=["BUG001"]),
     dict(name="test_appends_to_given_list", description="Explicit list is mutated and returned", category="normal", expected="[1, 2], same object", covers=[])],
)

_add(
    "security_sample", "SQL injection and eval()",
    "find_user looks users up by name; calculate evaluates simple arithmetic like '2+3*4'. Please audit this for security vulnerabilities.",
    '''
import sqlite3


def find_user(conn, name):
    cursor = conn.execute("SELECT id, name FROM users WHERE name = '" + name + "'")
    return cursor.fetchall()


def calculate(expression):
    return eval(expression)
''',
    [dict(title="SQL injection via string concatenation", severity="high", line_number=5,
          description="The name is concatenated into the SQL text, so input such as `' OR '1'='1` returns every row.",
          suggested_fix="Use a parameterised query: execute(sql, (name,)).", confidence=0.98, category="security"),
     dict(title="Arbitrary code execution through eval()", severity="high", line_number=10,
          description="eval() runs any Python expression, e.g. `__import__('os').system(...)`.",
          suggested_fix="Parse with ast and evaluate only numeric operators.", confidence=0.98, category="security")],
    [],
    '''
import ast
import operator
import sqlite3

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def find_user(conn, name):
    cursor = conn.execute("SELECT id, name FROM users WHERE name = ?", (name,))
    return cursor.fetchall()


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand)
    raise ValueError("unsupported expression")


def calculate(expression):
    return _eval_node(ast.parse(expression, mode="eval").body)
''',
    [dict(description="Parameterised the SQL query", reason="Values are passed separately from SQL text, preventing injection."),
     dict(description="Replaced eval() with an AST-based arithmetic evaluator", reason="Only numbers and + - * / are allowed; anything else raises ValueError.")],
    '''
import sqlite3

import pytest

from solution import calculate, find_user


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    c.executemany("INSERT INTO users (name) VALUES (?)", [("alice",), ("bob",)])
    return c


def test_find_existing_user(conn):
    assert find_user(conn, "alice") == [(1, "alice")]


def test_sql_injection_does_not_leak_rows(conn):
    assert find_user(conn, "' OR '1'='1") == []


def test_calculate_precedence():
    assert calculate("2+3*4") == 14


def test_calculate_rejects_code():
    with pytest.raises(ValueError):
        calculate("__import__('os')")
''',
    [dict(name="test_find_existing_user", description="Normal lookup", category="normal", expected="[(1, 'alice')]", covers=[]),
     dict(name="test_sql_injection_does_not_leak_rows", description="Injection payload returns no rows", category="regression", expected="[]", covers=["BUG001"]),
     dict(name="test_calculate_precedence", description="Arithmetic precedence", category="normal", expected="14", covers=[]),
     dict(name="test_calculate_rejects_code", description="Non-arithmetic input must raise ValueError", category="invalid", expected="ValueError", covers=["BUG002"])],
)

_add(
    "clean_code", "Correct, clean code (control sample)",
    "clamp limits a value to the inclusive range [low, high]. Please review this code.",
    '''
def clamp(value, low, high):
    """Limit value to the inclusive range [low, high]."""
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))
''',
    [], [], None, [],
    '''
import pytest

from solution import clamp


def test_inside_range():
    assert clamp(5, 0, 10) == 5


def test_below_and_above():
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10


def test_bounds_inclusive():
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10


def test_invalid_range():
    with pytest.raises(ValueError):
        clamp(1, 5, 0)
''',
    [dict(name="test_inside_range", description="Value within range unchanged", category="normal", expected="5", covers=[]),
     dict(name="test_below_and_above", description="Clamps both sides", category="boundary", expected="0 and 10", covers=[]),
     dict(name="test_bounds_inclusive", description="Bounds are inclusive", category="boundary", expected="unchanged", covers=[]),
     dict(name="test_invalid_range", description="low > high raises", category="invalid", expected="ValueError", covers=[])],
)


def list_samples() -> list[dict]:
    return [{k: s[k] for k in ("id", "title", "description", "code")} for s in SAMPLES.values()]


def match_sample(sample_id: str | None, code: str) -> dict | None:
    """Return the sample only if the submitted code is unchanged (otherwise predefined output would be wrong)."""
    s = SAMPLES.get(sample_id or "")
    if s and s["code"].strip() == (code or "").strip():
        return s
    return None
