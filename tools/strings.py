"""Lists every translatable string: _("...") calls and the category labels.

Used by tests/test_i18n.py; run directly to print the list.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def source_strings():
    found = set()
    for path in sorted((ROOT / "keyfinder").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    sys.path.insert(0, str(ROOT))
    from keyfinder.categories import CATEGORIES
    found.update(label for _id, label, _e, _w in CATEGORIES)
    return found


if __name__ == "__main__":
    for s in sorted(source_strings()):
        print(repr(s))
