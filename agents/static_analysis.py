"""Static code analysis: custom AST rules + Ruff, plus a transparent quality score.

Findings carry ``source="static"``. Line numbers always come from the tools, never from an LLM.
Python is analysed in depth; other languages get a small set of regex heuristics only.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict

SEVERITY_WEIGHT = {"critical": 20, "high": 12, "medium": 6, "low": 2, "info": 0}
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

SECRET_NAME = re.compile(r"(?i)(password|passwd|secret|api_?key|token|private_key)")
DANGEROUS_CALLS = {
    "eval": ("Use of eval()", "high", "eval() executes arbitrary expressions; use ast.literal_eval or a parser."),
    "exec": ("Use of exec()", "high", "exec() executes arbitrary code; avoid or restrict to trusted input."),
}

_ruff_cmd: list[str] | None | bool = False  # False = not probed yet


def _finding(rule, title, severity, line, description, category, tool="ast", fix=""):
    return {
        "rule": rule, "title": title, "severity": severity, "line_number": line,
        "description": description, "category": category, "source": "static",
        "tool": tool, "suggested_fix": fix, "confidence": 1.0 if tool == "ast" else 0.9,
    }


def _call_name(node: ast.Call) -> str:
    f = node.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def _has_exit(nodes: list[ast.stmt]) -> bool:
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, (ast.Break, ast.Return, ast.Raise)):
                return True
            if isinstance(sub, ast.Call) and _call_name(sub) in ("sys.exit", "exit", "quit", "os._exit"):
                return True
    return False


def _complexity(fn: ast.AST) -> int:
    score = 1
    for n in ast.walk(fn):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert)):
            score += 1
        elif isinstance(n, ast.BoolOp):
            score += len(n.values) - 1
        elif isinstance(n, ast.comprehension):
            score += 1 + len(n.ifs)
    return score


def _max_depth(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        inc = 1 if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)) else 0
        best = max(best, _max_depth(child, depth + inc))
    return best


def _is_str_building(arg: ast.AST) -> bool:
    if isinstance(arg, ast.JoinedStr):
        return True
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Add, ast.Mod)):
        return any(isinstance(x, (ast.Constant, ast.JoinedStr)) and (not isinstance(x, ast.Constant) or isinstance(x.value, str))
                   for x in (arg.left, arg.right))
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
        return True
    return False


def _analyze_python_ast(code: str) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    metrics = {"functions": [], "classes": 0, "imports": 0}
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        findings.append(_finding(
            "syntax-error", "Syntax error", "critical", exc.lineno,
            f"The code does not parse: {exc.msg}.", "bug", fix="Fix the syntax error so the code can run.",
        ))
        return findings, metrics

    func_bodies: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            length = end - node.lineno + 1
            cx = _complexity(node)
            depth = _max_depth(node)
            n_args = len(node.args.args) + len(node.args.kwonlyargs)
            metrics["functions"].append({
                "name": node.name, "line": node.lineno, "length": length,
                "complexity": cx, "max_nesting": depth, "args": n_args,
            })
            if length > 50:
                findings.append(_finding("long-function", f"Function '{node.name}' is {length} lines long", "low", node.lineno,
                                         "Long functions are hard to test and maintain.", "style", fix="Split into smaller functions."))
            if cx > 10:
                findings.append(_finding("high-complexity", f"Function '{node.name}' has cyclomatic complexity {cx}", "medium", node.lineno,
                                         "High branching makes the function error-prone and hard to test.", "complexity",
                                         fix="Extract helpers or simplify conditions."))
            if depth > 4:
                findings.append(_finding("deep-nesting", f"Function '{node.name}' nests {depth} levels deep", "low", node.lineno,
                                         "Deep nesting hurts readability.", "style", fix="Use early returns / guard clauses."))
            if n_args > 6:
                findings.append(_finding("many-arguments", f"Function '{node.name}' takes {n_args} arguments", "low", node.lineno,
                                         "Many parameters suggest the function does too much.", "style"))
            # mutable default arguments
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x is not None]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)) or (
                    isinstance(d, ast.Call) and _call_name(d) in ("list", "dict", "set")
                ):
                    findings.append(_finding(
                        "mutable-default-arg", f"Mutable default argument in '{node.name}'", "medium", d.lineno,
                        "A mutable default is created once and shared across calls, causing state to leak between calls.",
                        "bug", fix="Use None as the default and create the object inside the function."))
            # duplicate-body detection (names stripped)
            body_dump = "".join(ast.dump(s, annotate_fields=False) for s in node.body)
            body_dump = re.sub(r"Name\('[^']*'", "Name('_'", body_dump)
            if length >= 5:
                func_bodies[hashlib.md5(body_dump.encode()).hexdigest()].append((node.name, node.lineno))
        elif isinstance(node, ast.ClassDef):
            metrics["classes"] += 1
            if not re.match(r"^_?[A-Z][A-Za-z0-9]*$", node.name):
                findings.append(_finding("class-naming", f"Class '{node.name}' is not CapWords", "low", node.lineno,
                                         "PEP 8 recommends CapWords for class names.", "style"))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            metrics["imports"] += 1
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(_finding("bare-except", "Bare 'except:' clause", "medium", node.lineno,
                                         "Catches everything incl. KeyboardInterrupt/SystemExit and hides real errors.",
                                         "bug", fix="Catch specific exceptions."))
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(_finding("swallowed-exception", "Exception silently ignored", "low", node.lineno,
                                         "An except block that only passes hides failures.", "style"))
        elif isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators, strict=True):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    findings.append(_finding("none-comparison", "Comparison to None with ==/!=", "low", node.lineno,
                                             "Use 'is None' / 'is not None'.", "bug", fix="Replace with `is None`."))
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comp, ast.Constant) and isinstance(comp.value, (int, str, bytes)) \
                        and not isinstance(comp.value, bool):
                    findings.append(_finding("is-literal", "Identity comparison with a literal", "medium", node.lineno,
                                             "'is' compares object identity; use ==.", "bug", fix="Use == / !=."))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if isinstance(node.right, ast.Constant) and node.right.value == 0:
                findings.append(_finding("zero-division", "Division by literal zero", "high", node.lineno,
                                         "This expression always raises ZeroDivisionError.", "bug"))
        elif isinstance(node, ast.While):
            t = node.test
            if isinstance(t, ast.Constant) and t.value is True and not _has_exit(node.body):
                findings.append(_finding("infinite-loop", "'while True' loop with no exit", "high", node.lineno,
                                         "No break, return or raise inside the loop: it can never terminate.", "bug",
                                         fix="Add a termination condition."))
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in DANGEROUS_CALLS:
                title, sev, desc = DANGEROUS_CALLS[name]
                findings.append(_finding(f"dangerous-{name}", title, sev, node.lineno, desc, "security", fix=desc))
            elif name in ("os.system", "os.popen"):
                findings.append(_finding("os-system", f"Shell command via {name}()", "high", node.lineno,
                                         "Shell execution with unsanitised input enables command injection.", "security",
                                         fix="Use subprocess.run([...]) with an argument list and shell=False."))
            elif name.startswith("subprocess.") and any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in node.keywords
            ):
                findings.append(_finding("subprocess-shell", "subprocess call with shell=True", "high", node.lineno,
                                         "shell=True with dynamic input enables command injection.", "security",
                                         fix="Pass an argument list and shell=False."))
            elif name in ("pickle.load", "pickle.loads", "marshal.loads", "cPickle.loads"):
                findings.append(_finding("unsafe-deserialization", f"Unsafe deserialisation via {name}()", "high", node.lineno,
                                         "Deserialising untrusted data can execute arbitrary code.", "security",
                                         fix="Use JSON or another safe format."))
            elif name == "yaml.load" and not any(kw.arg == "Loader" for kw in node.keywords):
                findings.append(_finding("yaml-load", "yaml.load without a safe Loader", "high", node.lineno,
                                         "yaml.load can construct arbitrary objects.", "security", fix="Use yaml.safe_load."))
            elif name in ("hashlib.md5", "hashlib.sha1"):
                findings.append(_finding("weak-hash", f"Weak hash {name}()", "low", node.lineno,
                                         "MD5/SHA-1 are unsuitable for security purposes.", "security", fix="Use SHA-256 or better."))
            elif name.endswith(".execute") or name.endswith(".executemany"):
                if node.args and _is_str_building(node.args[0]):
                    findings.append(_finding("sql-injection", "SQL built with string formatting", "high", node.lineno,
                                             "Interpolating values into SQL allows SQL injection.", "security",
                                             fix="Use parameterised queries (placeholders)."))
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and node.value.value.strip():
                for tgt in node.targets:
                    tname = tgt.id if isinstance(tgt, ast.Name) else (tgt.attr if isinstance(tgt, ast.Attribute) else "")
                    if tname and SECRET_NAME.search(tname) and len(node.value.value) >= 4:
                        findings.append(_finding("hardcoded-secret", f"Hard-coded credential in '{tname}'", "high", node.lineno,
                                                 "Secrets in source code leak through version control.", "security",
                                                 fix="Load secrets from environment variables or a secret manager."))
        elif isinstance(node, ast.For):
            # off-by-one heuristics: range(len(x)+1) / x[i+1] inside `for i in range(len(x))`
            it = node.iter
            if isinstance(it, ast.Call) and _call_name(it) == "range" and it.args:
                last = it.args[-1] if len(it.args) < 3 else it.args[1]
                if isinstance(last, ast.BinOp) and isinstance(last.op, ast.Add) and isinstance(last.left, ast.Call) \
                        and _call_name(last.left) == "len":
                    findings.append(_finding(
                        "range-len-plus", "range(len(x) + n) may overrun the sequence", "medium", node.lineno,
                        "Iterating one past len() typically raises IndexError when used for indexing (heuristic).",
                        "bug", fix="Use range(len(x))."))
                if isinstance(last, ast.Call) and _call_name(last) == "len" and isinstance(node.target, ast.Name):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.BinOp) \
                                and isinstance(sub.slice.op, ast.Add) and isinstance(sub.slice.left, ast.Name) \
                                and sub.slice.left.id == node.target.id \
                                and isinstance(sub.slice.right, ast.Constant) and isinstance(sub.slice.right.value, int) \
                                and sub.slice.right.value > 0:
                            findings.append(_finding(
                                "index-past-end", "x[i+1] inside range(len(x)) will overrun on the last iteration", "medium",
                                sub.lineno, "On the final iteration i+1 equals len(x) (heuristic).", "bug",
                                fix="Iterate to len(x) - 1."))
                            break

    for entries in func_bodies.values():
        if len(entries) > 1:
            names = ", ".join(n for n, _ in entries)
            findings.append(_finding("duplicate-code", f"Duplicated function bodies: {names}", "low", entries[1][1],
                                     "Identical logic is repeated; extract a shared helper.", "style"))
    return findings, metrics


def _ruff_command() -> list[str] | None:
    global _ruff_cmd
    if _ruff_cmd is False:
        exe = shutil.which("ruff")
        if exe:
            _ruff_cmd = [exe]
        else:
            try:
                ok = subprocess.run([sys.executable, "-m", "ruff", "--version"], capture_output=True, timeout=10).returncode == 0
            except Exception:
                ok = False
            _ruff_cmd = [sys.executable, "-m", "ruff"] if ok else None
    return _ruff_cmd or None


RUFF_SELECT = "F,E,W,B,N,SIM"
RUFF_IGNORE = "B006,E722,E711,E712,E501,W292,W391"  # covered by AST rules or noisy for pasted snippets


def _ruff_findings(code: str) -> list[dict]:
    cmd = _ruff_command()
    if not cmd:
        return []
    try:
        proc = subprocess.run(
            cmd + ["check", "--stdin-filename", "submitted.py", "--output-format", "json", "--select", RUFF_SELECT,
                   "--ignore", RUFF_IGNORE, "--no-cache", "-"],
            input=code, capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout or "[]")
    except Exception:
        return []
    out = []
    for d in data:
        rule = d.get("code") or "RUFF"
        if rule == "invalid-syntax" or d.get("code") is None:
            continue  # handled by the AST pass
        category = "bug" if rule.startswith(("F82", "F63", "F5", "F7", "F6", "B")) else "style"
        sev = "medium" if category == "bug" else "low"
        line = (d.get("location") or {}).get("row")
        out.append(_finding(f"ruff:{rule}", d.get("message", rule), sev, line,
                            f"Ruff rule {rule}. {d.get('message', '')}", category, tool="ruff",
                            fix=(d.get("fix") or {}).get("message", "") or ""))
    return out


_C_UNSAFE = {
    "gets": "gets() cannot bound input and was removed from C11; use fgets().",
    "strcpy": "strcpy() does not check bounds; use strncpy()/snprintf().",
    "strcat": "strcat() does not check bounds; use strncat().",
    "sprintf": "sprintf() can overflow; use snprintf().",
    "system": "system() with dynamic input enables command injection.",
}


def _analyze_other(code: str, language: str) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    lines = code.splitlines()
    if language == "c":
        for i, line in enumerate(lines, 1):
            for fn, why in _C_UNSAFE.items():
                if re.search(rf"\b{fn}\s*\(", line):
                    findings.append(_finding(f"c-unsafe-{fn}", f"Unsafe C function {fn}()", "high", i, why, "security"))
    if language == "java":
        for i, line in enumerate(lines, 1):
            if re.search(r"catch\s*\(\s*(Exception|Throwable)\s+\w+\s*\)\s*\{\s*\}", line):
                findings.append(_finding("java-empty-catch", "Empty catch block", "medium", i, "Swallows exceptions.", "bug"))
            if re.search(r'"\s*\+\s*\w+.*(executeQuery|executeUpdate)|(executeQuery|executeUpdate)\(\s*".*"\s*\+', line):
                findings.append(_finding("java-sqli", "SQL built by string concatenation", "high", i,
                                         "Use PreparedStatement.", "security"))
    return findings, {"functions": [], "classes": 0, "imports": 0, "note": f"Limited heuristic analysis for {language}."}


def analyze(code: str, language: str = "python") -> dict:
    """Run static analysis. Returns {findings, metrics, tools}."""
    language = (language or "python").lower()
    if language != "python":
        f, m = _analyze_other(code, language)
        m["loc"] = len([ln for ln in code.splitlines() if ln.strip()])
        return {"findings": _number(f), "metrics": m, "tools": ["regex-heuristics"]}
    f, m = _analyze_python_ast(code)
    tools = ["python-ast"]
    if not any(x["rule"] == "syntax-error" for x in f):
        rf = _ruff_findings(code)
        if rf or _ruff_command():
            tools.append("ruff")
        f += rf
    m["loc"] = len([ln for ln in code.splitlines() if ln.strip()])
    return {"findings": _number(f), "metrics": m, "tools": tools}


def _number(findings: list[dict]) -> list[dict]:
    findings.sort(key=lambda x: (SEVERITY_ORDER.index(x["severity"]), x["line_number"] or 0))
    for i, f in enumerate(findings, 1):
        f["id"] = f"STA{i:03d}"
    return findings


def compute_quality_score(issues: list[dict], style_issues: list[dict], metrics: dict) -> dict:
    """Deterministic, transparent 0-100 score. No LLM involved.

    100 - sum(severity weight of bug/security issues)
        - min(25, 1.5 * number of style findings)
        - 3 per function with cyclomatic complexity > 10
    """
    bug_pen = sum(SEVERITY_WEIGHT.get(i.get("severity", "low"), 2) for i in issues)
    style_pen = min(25.0, 1.5 * len(style_issues))
    cx_pen = 3 * sum(1 for f in metrics.get("functions", []) if f.get("complexity", 0) > 10)
    score = max(0, round(100 - bug_pen - style_pen - cx_pen))
    return {
        "score": score,
        "breakdown": {"bug_security_penalty": bug_pen, "style_penalty": round(style_pen, 1), "complexity_penalty": cx_pen},
        "formula": "100 - Σ severity weights(bug/security issues) - min(25, 1.5×style findings) - 3×(functions with complexity>10)",
    }
