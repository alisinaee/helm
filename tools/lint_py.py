"""Lint the Python sources: syntax, stdlib-only imports, the layering rule, and style rules.

Rules: only stdlib or roadmap imports; core imports nothing from the project; store imports core/store-level
modules only, and so on up to commands; no shell=True; no bare except outside roadmap/commands/hook.py;
no print() outside roadmap/commands/ and roadmap/cli.py; a module docstring in every file; 120 columns;
LF line endings; a final newline. Run it directly or through tools/check.py.
"""

import ast
import importlib.util
import os
import sys
import sysconfig

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_COLS = 120
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}
LOCAL_TOPS = {"roadmap", "tests", "tools"}

# Which roadmap layers each layer may import. core imports nothing from the project.
ALLOWED = {
    "core": set(),
    "store": {"core", "errors", "log"},
    "services": {"core", "store", "errors", "log"},
    "http": {"core", "store", "services", "errors", "log"},
    "commands": {"core", "store", "services", "http", "errors", "log"},
    "errors": set(),
    "log": set(),
    "cli": {"commands", "errors", "log"},
    "__main__": {"cli"},
    "__init__": set(),
}
BARE_EXCEPT_OK = {"roadmap/commands/hook.py"}


def _layer(rel_in_package):
    parts = rel_in_package.split("/")
    return parts[0][:-3] if len(parts) == 1 else parts[0]


def _print_ok(rel):
    if not rel.startswith("roadmap/"):
        return True
    return rel.startswith("roadmap/commands/") or rel == "roadmap/cli.py"


def _is_stdlib(top):
    if top in sys.builtin_module_names or top in getattr(sys, "stdlib_module_names", ()):
        return True
    try:
        spec = importlib.util.find_spec(top)
    except (ImportError, ValueError):
        return False
    if spec is None:
        return False
    origin = spec.origin or ""
    if origin in ("built-in", "frozen"):
        return True
    return origin.startswith(sysconfig.get_paths()["stdlib"]) and "site-packages" not in origin


def _check_import(node, path, rel, issues):
    if isinstance(node, ast.Import):
        candidates = [alias.name for alias in node.names]
    elif node.level:
        issues.append(f"{rel}:{node.lineno}: use absolute imports, not relative ones")
        return
    elif node.module == "roadmap":
        candidates = ["roadmap." + alias.name for alias in node.names]
    else:
        candidates = [node.module or ""]
    for dotted in candidates:
        top = dotted.split(".")[0]
        if top == "roadmap":
            if rel.startswith("roadmap/") and "." in dotted:
                src = _layer(rel[len("roadmap/"):])
                target = dotted.split(".")[1]
                if src not in ALLOWED:
                    issues.append(f"{rel}: unknown layer '{src}'")
                elif target in ALLOWED and target != src and target not in ALLOWED[src]:
                    issues.append(f"{rel}:{node.lineno}: layering: {src} may not import {target}")
            continue
        if top in LOCAL_TOPS or os.path.exists(os.path.join(os.path.dirname(path), top + ".py")):
            continue
        if not _is_stdlib(top):
            issues.append(f"{rel}:{node.lineno}: import of non-stdlib module '{top}'")


def _check_file(path, rel, issues):
    with open(path, "rb") as fh:
        raw = fh.read()
    if b"\r" in raw:
        issues.append(f"{rel}: CR characters found (use LF line endings)")
    if raw and not raw.endswith(b"\n"):
        issues.append(f"{rel}: missing final newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        issues.append(f"{rel}: not valid UTF-8")
        return
    for number, line in enumerate(text.split("\n"), 1):
        if len(line) > MAX_COLS:
            issues.append(f"{rel}:{number}: longer than {MAX_COLS} columns")
    try:
        tree = ast.parse(raw, filename=path)
    except (SyntaxError, ValueError) as exc:
        issues.append(f"{rel}: does not parse: {exc}")
        return
    if not ast.get_docstring(tree):
        issues.append(f"{rel}: missing module docstring")
    if rel.startswith("roadmap/") and _layer(rel[len("roadmap/"):]) not in ALLOWED:
        issues.append(f"{rel}: unknown layer")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    issues.append(f"{rel}:{node.lineno}: shell=True is not allowed")
            if isinstance(node.func, ast.Name) and node.func.id == "print" and not _print_ok(rel):
                issues.append(f"{rel}:{node.lineno}: print() is allowed only in roadmap/commands/ and cli.py")
        elif isinstance(node, ast.ExceptHandler) and node.type is None and rel not in BARE_EXCEPT_OK:
            issues.append(f"{rel}:{node.lineno}: bare except is not allowed")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            _check_import(node, path, rel, issues)


def run(repo=REPO):
    """Return a list of issue strings; an empty list means clean."""
    issues = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, repo).replace(os.sep, "/")
                _check_file(path, rel, issues)
    return issues


def main():
    """Print the issues and return the exit code."""
    issues = run()
    for issue in issues:
        print(issue)
    print("lint_py: " + ("ok" if not issues else str(len(issues)) + " issue(s)"))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
