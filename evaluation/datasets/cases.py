"""Benchmark dataset: 34 deliberately designed programs.

kind:
  correct     - no defect; any bug/security flag is a FALSE POSITIVE
  functional  - behavioural bug (logic / boundary / runtime / edge); reference tests FAIL on `code`, PASS on `fixed`
  security    - vulnerability with a behavioural symptom; reference tests FAIL on `code`, PASS on `fixed`
  style       - functionally correct but poorly structured; reference tests pass on both

`bug_lines` are the 1-based lines of the defect (used for localisation accuracy).
`regressed` (optional) is a plausible-but-wrong "fix" that breaks previously-passing tests; used to measure regression detection.
Every case is machine-checked by `python -m evaluation.benchmark --validate-dataset`.
"""
from __future__ import annotations

CASES: list[dict] = []


def C(id, category, kind, spec, code, tests, fixed=None, bug_lines=(), regressed=None):
    CASES.append(dict(id=id, category=category, kind=kind, spec=spec, code=code.strip("\n") + "\n",
                      tests=tests.strip("\n") + "\n", fixed=(fixed.strip("\n") + "\n") if fixed else None,
                      bug_lines=list(bug_lines), regressed=(regressed.strip("\n") + "\n") if regressed else None))


# ------------------------------------------------------------------ correct programs (6)
C("ok_clamp", "correct", "correct", "Clamp value to [low, high].",
  'def clamp(value, low, high):\n    """Clamp value into [low, high]."""\n    if low > high:\n        raise ValueError("bad range")\n    return max(low, min(value, high))\n',
  "import pytest\nfrom solution import clamp\n\ndef test_in():\n    assert clamp(5, 0, 10) == 5\n\ndef test_edges():\n    assert clamp(-1, 0, 10) == 0\n    assert clamp(11, 0, 10) == 10\n\ndef test_bad():\n    with pytest.raises(ValueError):\n        clamp(1, 2, 1)\n")
C("ok_is_even", "correct", "correct", "True if n is even.",
  'def is_even(n):\n    """Return True when n is even."""\n    return n % 2 == 0\n',
  "from solution import is_even\n\ndef test_even():\n    assert is_even(4) and is_even(0) and is_even(-2)\n\ndef test_odd():\n    assert not is_even(3) and not is_even(-1)\n")
C("ok_factorial", "correct", "correct", "Iterative factorial; negative input raises ValueError.",
  'def factorial(n):\n    """Return n!."""\n    if n < 0:\n        raise ValueError("n must be >= 0")\n    result = 1\n    for k in range(2, n + 1):\n        result *= k\n    return result\n',
  "import pytest\nfrom solution import factorial\n\ndef test_small():\n    assert factorial(0) == 1\n    assert factorial(1) == 1\n    assert factorial(5) == 120\n\ndef test_negative():\n    with pytest.raises(ValueError):\n        factorial(-1)\n")
C("ok_reverse_words", "correct", "correct", "Reverse the order of words in a sentence.",
  'def reverse_words(sentence):\n    """Reverse word order."""\n    return " ".join(reversed(sentence.split()))\n',
  'from solution import reverse_words\n\ndef test_basic():\n    assert reverse_words("a b c") == "c b a"\n\ndef test_spaces_and_empty():\n    assert reverse_words("  hi   there ") == "there hi"\n    assert reverse_words("") == ""\n')
C("ok_gcd", "correct", "correct", "Greatest common divisor (Euclid).",
  'def gcd(a, b):\n    """Return gcd(a, b) for non-negative integers."""\n    while b:\n        a, b = b, a % b\n    return a\n',
  "from solution import gcd\n\ndef test_basic():\n    assert gcd(12, 18) == 6\n    assert gcd(7, 13) == 1\n\ndef test_zero():\n    assert gcd(0, 5) == 5\n    assert gcd(5, 0) == 5\n")
C("ok_merge_sorted", "correct", "correct", "Merge two sorted lists into one sorted list.",
  'def merge_sorted(a, b):\n    """Merge two sorted lists."""\n    i = j = 0\n    out = []\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            out.append(a[i])\n            i += 1\n        else:\n            out.append(b[j])\n            j += 1\n    out.extend(a[i:])\n    out.extend(b[j:])\n    return out\n',
  "from solution import merge_sorted\n\ndef test_basic():\n    assert merge_sorted([1, 3, 5], [2, 4]) == [1, 2, 3, 4, 5]\n\ndef test_empty_sides():\n    assert merge_sorted([], [1]) == [1]\n    assert merge_sorted([1], []) == [1]\n    assert merge_sorted([], []) == []\n")

# ------------------------------------------------------------------ logic bugs (7)
C("logic_palindrome", "logic", "functional", "is_palindrome ignores case and non-alphanumeric characters.",
  'def is_palindrome(s):\n    """Case-insensitive palindrome check ignoring punctuation."""\n    return s == s[::-1]\n',
  'from solution import is_palindrome\n\ndef test_plain():\n    assert is_palindrome("level")\n\ndef test_sentence():\n    assert is_palindrome("A man, a plan, a canal: Panama")\n\ndef test_not():\n    assert not is_palindrome("hello")\n',
  'def is_palindrome(s):\n    """Case-insensitive palindrome check ignoring punctuation."""\n    cleaned = [c.lower() for c in s if c.isalnum()]\n    return cleaned == cleaned[::-1]\n', [3])
C("logic_find_max", "logic", "functional", "find_max returns the largest element; None for an empty list.",
  'def find_max(items):\n    """Largest element, or None if empty."""\n    if not items:\n        return None\n    best = items[0]\n    for x in items:\n        if x < best:\n            best = x\n    return best\n',
  "from solution import find_max\n\ndef test_basic():\n    assert find_max([3, 9, 2]) == 9\n\ndef test_negative():\n    assert find_max([-5, -2, -9]) == -2\n\ndef test_empty():\n    assert find_max([]) is None\n",
  'def find_max(items):\n    """Largest element, or None if empty."""\n    if not items:\n        return None\n    best = items[0]\n    for x in items:\n        if x > best:\n            best = x\n    return best\n', [7])
C("logic_vowels", "logic", "functional", "count_vowels counts vowels case-insensitively.",
  'def count_vowels(s):\n    """Number of vowels (a, e, i, o, u) in s, any case."""\n    return sum(1 for c in s if c in "aeiou")\n',
  'from solution import count_vowels\n\ndef test_lower():\n    assert count_vowels("hello") == 2\n\ndef test_upper():\n    assert count_vowels("HELLO") == 2\n\ndef test_none():\n    assert count_vowels("rhythm") == 0\n',
  'def count_vowels(s):\n    """Number of vowels (a, e, i, o, u) in s, any case."""\n    return sum(1 for c in s.lower() if c in "aeiou")\n', [3],
  regressed='def count_vowels(s):\n    return sum(1 for c in s if c in "AEIOU")\n')
C("logic_leap_year", "logic", "functional", "is_leap_year follows the Gregorian rules (divisible by 400 is leap).",
  'def is_leap_year(year):\n    """Gregorian leap-year test."""\n    return year % 4 == 0 and year % 100 != 0\n',
  "from solution import is_leap_year\n\ndef test_common():\n    assert is_leap_year(2024)\n    assert not is_leap_year(2023)\n\ndef test_century():\n    assert not is_leap_year(1900)\n    assert is_leap_year(2000)\n",
  'def is_leap_year(year):\n    """Gregorian leap-year test."""\n    return year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)\n', [3])
C("logic_fizzbuzz", "logic", "functional", "fizzbuzz(n): 'FizzBuzz' for multiples of 15, 'Fizz' for 3, 'Buzz' for 5, else str(n).",
  'def fizzbuzz(n):\n    """FizzBuzz for a single number."""\n    if n % 3 == 0:\n        return "Fizz"\n    if n % 5 == 0:\n        return "Buzz"\n    if n % 15 == 0:\n        return "FizzBuzz"\n    return str(n)\n',
  'from solution import fizzbuzz\n\ndef test_basic():\n    assert fizzbuzz(3) == "Fizz"\n    assert fizzbuzz(5) == "Buzz"\n    assert fizzbuzz(7) == "7"\n\ndef test_both():\n    assert fizzbuzz(15) == "FizzBuzz"\n',
  'def fizzbuzz(n):\n    """FizzBuzz for a single number."""\n    if n % 15 == 0:\n        return "FizzBuzz"\n    if n % 3 == 0:\n        return "Fizz"\n    if n % 5 == 0:\n        return "Buzz"\n    return str(n)\n', [3])
C("logic_dedupe_order", "logic", "functional", "remove_duplicates keeps the FIRST occurrence and preserves order.",
  'def remove_duplicates(items):\n    """De-duplicate preserving first-occurrence order."""\n    return list(set(items))\n',
  "from solution import remove_duplicates\n\ndef test_order():\n    assert remove_duplicates([3, 1, 3, 2, 1]) == [3, 1, 2]\n\ndef test_empty():\n    assert remove_duplicates([]) == []\n",
  'def remove_duplicates(items):\n    """De-duplicate preserving first-occurrence order."""\n    seen = set()\n    out = []\n    for x in items:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n', [3])
C("logic_mutable_default", "logic", "functional", "add_item appends to a fresh list when none is given.",
  'def add_item(item, items=[]):\n    """Append item and return the list."""\n    items.append(item)\n    return items\n',
  "from solution import add_item\n\ndef test_fresh():\n    assert add_item(1) == [1]\n    assert add_item(2) == [2]\n\ndef test_given():\n    lst = [1]\n    assert add_item(2, lst) == [1, 2]\n",
  'def add_item(item, items=None):\n    """Append item and return the list."""\n    if items is None:\n        items = []\n    items.append(item)\n    return items\n', [1])

# ------------------------------------------------------------------ boundary-condition errors (5)
C("bound_binary_search", "boundary", "functional", "Return index of target in a sorted list, else -1.",
  'def binary_search(items, target):\n    """Index of target or -1."""\n    low, high = 0, len(items) - 1\n    while low < high:\n        mid = (low + high) // 2\n        if items[mid] == target:\n            return mid\n        if items[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1\n',
  "from solution import binary_search\n\ndef test_single():\n    assert binary_search([5], 5) == 0\n\ndef test_last():\n    assert binary_search([1, 3, 5, 7], 7) == 3\n\ndef test_missing():\n    assert binary_search([1, 3], 2) == -1\n    assert binary_search([], 1) == -1\n",
  'def binary_search(items, target):\n    """Index of target or -1."""\n    low, high = 0, len(items) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if items[mid] == target:\n            return mid\n        if items[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1\n', [4])
C("bound_last_n", "boundary", "functional", "last_n(items, n) returns the last n items; n <= 0 returns [].",
  'def last_n(items, n):\n    """Last n items."""\n    return items[-n:]\n',
  "from solution import last_n\n\ndef test_basic():\n    assert last_n([1, 2, 3, 4], 2) == [3, 4]\n\ndef test_zero():\n    assert last_n([1, 2, 3], 0) == []\n\ndef test_too_many():\n    assert last_n([1, 2], 5) == [1, 2]\n",
  'def last_n(items, n):\n    """Last n items."""\n    if n <= 0:\n        return []\n    return items[-n:]\n', [3])
C("bound_sum_range", "boundary", "functional", "sum_range(a, b) sums integers from a to b INCLUSIVE; 0 if a > b.",
  'def sum_range(a, b):\n    """Inclusive sum of a..b."""\n    return sum(range(a, b))\n',
  "from solution import sum_range\n\ndef test_inclusive():\n    assert sum_range(1, 3) == 6\n\ndef test_single():\n    assert sum_range(2, 2) == 2\n\ndef test_reversed():\n    assert sum_range(3, 1) == 0\n",
  'def sum_range(a, b):\n    """Inclusive sum of a..b."""\n    return sum(range(a, b + 1))\n', [3],
  regressed='def sum_range(a, b):\n    return sum(range(min(a, b), max(a, b) + 1))\n')
C("bound_chunk", "boundary", "functional", "chunk(items, size) splits into lists of at most size; the last chunk may be shorter.",
  'def chunk(items, size):\n    """Split into chunks."""\n    return [items[i:i + size] for i in range(0, len(items) - size, size)]\n',
  "from solution import chunk\n\ndef test_even():\n    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]\n\ndef test_remainder():\n    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\n\ndef test_empty():\n    assert chunk([], 3) == []\n",
  'def chunk(items, size):\n    """Split into chunks."""\n    return [items[i:i + size] for i in range(0, len(items), size)]\n', [3])
C("bound_grade", "boundary", "functional", "grade(score): 'A' for >= 90, 'B' for >= 80, else 'C'.",
  'def grade(score):\n    """Letter grade."""\n    if score > 90:\n        return "A"\n    if score > 80:\n        return "B"\n    return "C"\n',
  'from solution import grade\n\ndef test_inside():\n    assert grade(95) == "A"\n    assert grade(85) == "B"\n    assert grade(50) == "C"\n\ndef test_edges():\n    assert grade(90) == "A"\n    assert grade(80) == "B"\n',
  'def grade(score):\n    """Letter grade."""\n    if score >= 90:\n        return "A"\n    if score >= 80:\n        return "B"\n    return "C"\n', [3, 5])

# ------------------------------------------------------------------ runtime errors (6)
C("rt_average_empty", "runtime", "functional", "average of numbers; ValueError for an empty list.",
  'def average(numbers):\n    """Arithmetic mean."""\n    total = 0\n    for n in numbers:\n        total += n\n    return total / len(numbers)\n',
  "import pytest\nfrom solution import average\n\ndef test_basic():\n    assert average([1, 2, 3]) == 2\n\ndef test_empty():\n    with pytest.raises(ValueError):\n        average([])\n",
  'def average(numbers):\n    """Arithmetic mean."""\n    if not numbers:\n        raise ValueError("empty")\n    return sum(numbers) / len(numbers)\n', [6])
C("rt_second_largest", "runtime", "functional", "second_largest returns the second largest distinct value, or None if there are fewer than 2 distinct values.",
  'def second_largest(items):\n    """Second largest distinct value."""\n    ordered = sorted(set(items), reverse=True)\n    return ordered[1]\n',
  "from solution import second_largest\n\ndef test_basic():\n    assert second_largest([1, 5, 3]) == 3\n\ndef test_duplicates():\n    assert second_largest([4, 4, 2]) == 2\n\ndef test_short():\n    assert second_largest([7]) is None\n    assert second_largest([2, 2]) is None\n",
  'def second_largest(items):\n    """Second largest distinct value."""\n    ordered = sorted(set(items), reverse=True)\n    return ordered[1] if len(ordered) > 1 else None\n', [4])
C("rt_get_value", "runtime", "functional", "get_value(d, key, default=None) returns d[key] or the default when missing.",
  'def get_value(d, key, default=None):\n    """Dictionary lookup with default."""\n    return d[key]\n',
  "from solution import get_value\n\ndef test_present():\n    assert get_value({'a': 1}, 'a') == 1\n\ndef test_missing():\n    assert get_value({'a': 1}, 'b', 0) == 0\n    assert get_value({}, 'x') is None\n",
  'def get_value(d, key, default=None):\n    """Dictionary lookup with default."""\n    return d.get(key, default)\n', [3],
  regressed='def get_value(d, key, default=None):\n    return default\n')
C("rt_parse_ints", "runtime", "functional", "parse_int_list('1,2,x') returns the valid integers [1, 2], skipping invalid tokens.",
  'def parse_int_list(text):\n    """Parse comma separated integers, skipping invalid tokens."""\n    return [int(tok) for tok in text.split(",")]\n',
  "from solution import parse_int_list\n\ndef test_valid():\n    assert parse_int_list('1,2,3') == [1, 2, 3]\n\ndef test_invalid_skipped():\n    assert parse_int_list('1,x,3') == [1, 3]\n    assert parse_int_list('') == []\n",
  'def parse_int_list(text):\n    """Parse comma separated integers, skipping invalid tokens."""\n    out = []\n    for tok in text.split(","):\n        try:\n            out.append(int(tok))\n        except ValueError:\n            continue\n    return out\n', [3])
C("rt_pairwise_sum", "runtime", "functional", "pairwise_sum([1,2,3]) -> [3, 5] (sum of each adjacent pair).",
  'def pairwise_sum(items):\n    """Sums of adjacent pairs."""\n    out = []\n    for i in range(len(items)):\n        out.append(items[i] + items[i + 1])\n    return out\n',
  "from solution import pairwise_sum\n\ndef test_basic():\n    assert pairwise_sum([1, 2, 3]) == [3, 5]\n\ndef test_short():\n    assert pairwise_sum([1]) == []\n    assert pairwise_sum([]) == []\n",
  'def pairwise_sum(items):\n    """Sums of adjacent pairs."""\n    out = []\n    for i in range(len(items) - 1):\n        out.append(items[i] + items[i + 1])\n    return out\n', [4, 5])
C("rt_last_char", "runtime", "functional", "last_char(s) returns the last character, or '' for an empty string.",
  'def last_char(s):\n    """Last character."""\n    return s[len(s) - 1]\n',
  "from solution import last_char\n\ndef test_basic():\n    assert last_char('abc') == 'c'\n\ndef test_empty():\n    assert last_char('') == ''\n",
  'def last_char(s):\n    """Last character."""\n    return s[-1:] \n', [3])

# ------------------------------------------------------------------ edge-case failures (3)
C("edge_median", "edge", "functional", "median of a non-empty list; for even length, the mean of the two middle values.",
  'def median(items):\n    """Median value."""\n    ordered = sorted(items)\n    return ordered[len(ordered) // 2]\n',
  "from solution import median\n\ndef test_odd():\n    assert median([3, 1, 2]) == 2\n\ndef test_even():\n    assert median([1, 2, 3, 4]) == 2.5\n",
  'def median(items):\n    """Median value."""\n    ordered = sorted(items)\n    mid = len(ordered) // 2\n    if len(ordered) % 2:\n        return ordered[mid]\n    return (ordered[mid - 1] + ordered[mid]) / 2\n', [4])
C("edge_safe_div", "edge", "functional", "safe_div(a, b) returns None when b == 0.",
  'def safe_div(a, b):\n    """Division returning None for a zero divisor."""\n    return a / b\n',
  "from solution import safe_div\n\ndef test_basic():\n    assert safe_div(6, 3) == 2\n\ndef test_zero():\n    assert safe_div(1, 0) is None\n",
  'def safe_div(a, b):\n    """Division returning None for a zero divisor."""\n    if b == 0:\n        return None\n    return a / b\n', [3],
  regressed='def safe_div(a, b):\n    return None\n')
C("edge_flatten", "edge", "functional", "flatten(nested) flattens lists nested to ANY depth.",
  'def flatten(nested):\n    """Flatten arbitrarily nested lists."""\n    out = []\n    for x in nested:\n        if isinstance(x, list):\n            out.extend(x)\n        else:\n            out.append(x)\n    return out\n',
  "from solution import flatten\n\ndef test_flat():\n    assert flatten([1, 2]) == [1, 2]\n\ndef test_deep():\n    assert flatten([1, [2, [3, [4]]]]) == [1, 2, 3, 4]\n",
  'def flatten(nested):\n    """Flatten arbitrarily nested lists."""\n    out = []\n    for x in nested:\n        if isinstance(x, list):\n            out.extend(flatten(x))\n        else:\n            out.append(x)\n    return out\n', [6, 7])

# ------------------------------------------------------------------ security vulnerabilities (4)
C("sec_sql_injection", "security", "security", "find_user(conn, name) returns rows whose name equals `name` exactly.",
  'def find_user(conn, name):\n    """Look a user up by name."""\n    cur = conn.execute("SELECT id, name FROM users WHERE name = \'" + name + "\'")\n    return cur.fetchall()\n',
  "import sqlite3\nimport pytest\nfrom solution import find_user\n\n@pytest.fixture\ndef conn():\n    c = sqlite3.connect(':memory:')\n    c.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')\n    c.executemany('INSERT INTO users (name) VALUES (?)', [('alice',), ('bob',)])\n    return c\n\ndef test_lookup(conn):\n    assert find_user(conn, 'alice') == [(1, 'alice')]\n\ndef test_injection(conn):\n    assert find_user(conn, \"' OR '1'='1\") == []\n",
  'def find_user(conn, name):\n    """Look a user up by name."""\n    cur = conn.execute("SELECT id, name FROM users WHERE name = ?", (name,))\n    return cur.fetchall()\n', [3])
C("sec_eval", "security", "security", "parse_number(text) converts numeric text to float; anything else raises ValueError.",
  'def parse_number(text):\n    """Parse a number."""\n    return eval(text)\n',
  "import pytest\nfrom solution import parse_number\n\ndef test_number():\n    assert parse_number('3.5') == 3.5\n\ndef test_code_rejected():\n    with pytest.raises(ValueError):\n        parse_number(\"__import__('os')\")\n",
  'def parse_number(text):\n    """Parse a number."""\n    return float(text)\n', [3])
C("sec_path_traversal", "security", "security", "read_user_file(base_dir, name) reads a file INSIDE base_dir; names escaping it raise ValueError.",
  'import os\n\n\ndef read_user_file(base_dir, name):\n    """Read a file from base_dir."""\n    with open(os.path.join(base_dir, name), encoding="utf-8") as fh:\n        return fh.read()\n',
  "import pytest\nfrom solution import read_user_file\n\ndef test_inside(tmp_path):\n    (tmp_path / 'a.txt').write_text('hi')\n    assert read_user_file(str(tmp_path), 'a.txt') == 'hi'\n\ndef test_traversal(tmp_path):\n    base = tmp_path / 'base'\n    base.mkdir()\n    (tmp_path / 'secret.txt').write_text('s')\n    with pytest.raises(ValueError):\n        read_user_file(str(base), '../secret.txt')\n",
  'import os\n\n\ndef read_user_file(base_dir, name):\n    """Read a file from base_dir."""\n    root = os.path.realpath(base_dir)\n    path = os.path.realpath(os.path.join(root, name))\n    if os.path.commonpath([root, path]) != root:\n        raise ValueError("path escapes base directory")\n    with open(path, encoding="utf-8") as fh:\n        return fh.read()\n', [6])
C("sec_hardcoded_secret", "security", "security", "get_api_key() returns the API key from the API_KEY environment variable; RuntimeError if unset.",
  'def get_api_key():\n    """Return the API key."""\n    api_key = "sk_live_51HxExampleHardcodedKey"\n    return api_key\n',
  "import pytest\nfrom solution import get_api_key\n\ndef test_reads_env(monkeypatch):\n    monkeypatch.setenv('API_KEY', 'from-env')\n    assert get_api_key() == 'from-env'\n\ndef test_unset(monkeypatch):\n    monkeypatch.delenv('API_KEY', raising=False)\n    with pytest.raises(RuntimeError):\n        get_api_key()\n",
  'import os\n\n\ndef get_api_key():\n    """Return the API key."""\n    key = os.environ.get("API_KEY")\n    if not key:\n        raise RuntimeError("API_KEY is not set")\n    return key\n', [3])

# ------------------------------------------------------------------ poorly structured code (3): functionally correct
C("style_calc", "style", "style", "Calc(x, y) divides x by y and returns None for a zero divisor.",
  'def Calc(X, Y):\n    unused = 5\n    try:\n        return X / Y\n    except:\n        return None\n',
  "from solution import Calc\n\ndef test_ok():\n    assert Calc(4, 2) == 2\n\ndef test_zero():\n    assert Calc(1, 0) is None\n",
  'def calc(x, y):\n    """Divide x by y; None if y is zero."""\n    try:\n        return x / y\n    except ZeroDivisionError:\n        return None\n\n\nCalc = calc  # backwards-compatible alias\n', [1, 2, 5])
C("style_duplicate", "style", "style", "Two functions compute areas; they must keep working.",
  'def area_rect(w, h):\n    if w < 0 or h < 0:\n        raise ValueError("negative")\n    result = w * h\n    return result\n\n\ndef area_box(w, h):\n    if w < 0 or h < 0:\n        raise ValueError("negative")\n    result = w * h\n    return result\n',
  "import pytest\nfrom solution import area_box, area_rect\n\ndef test_values():\n    assert area_rect(2, 3) == 6\n    assert area_box(2, 3) == 6\n\ndef test_negative():\n    with pytest.raises(ValueError):\n        area_rect(-1, 2)\n    with pytest.raises(ValueError):\n        area_box(1, -2)\n",
  'def _area(w, h):\n    if w < 0 or h < 0:\n        raise ValueError("negative")\n    return w * h\n\n\ndef area_rect(w, h):\n    return _area(w, h)\n\n\ndef area_box(w, h):\n    return _area(w, h)\n', [1, 8])
C("style_none_compare", "style", "style", "describe(x) returns 'none' for None, else 'value'.",
  'def describe(x):\n    if x == None:\n        return "none"\n    else:\n        return "value"\n',
  "from solution import describe\n\ndef test_none():\n    assert describe(None) == 'none'\n\ndef test_value():\n    assert describe(0) == 'value'\n",
  'def describe(x):\n    """Describe whether x is None."""\n    return "none" if x is None else "value"\n', [2])
