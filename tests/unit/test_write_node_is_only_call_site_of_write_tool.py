"""T16 (G5+G6 stage spec); widened T18 (G8 stage spec, D-G8-11): the
write-capable callable is referenced in exactly one node factory
(`make_write_and_readback_node`), invoked exactly once, and is not a
parameter of the Write Guard node -- the guard authorizes, it does not
write (`CLAUDE.md` section 4).

G8 widened the scan from `nodes.py` alone to all of `src/lantern/graph/**`:
the compensation split (D-G8-11) added `compensation_nodes.py` to the
same package, and the ORIGINAL scan (parsing only `nodes.py`'s own source)
would not have seen a second write call site added in that new module at
all -- a real hole, found at this stage's kickoff, independent of
compensation itself. `test_synthetic_second_module_violation_is_detected`
below proves the widened scan actually catches it, not merely that no
real file currently violates it.
"""

import ast
import inspect
from typing import List

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph import nodes

GRAPH_DIR = PROJECT_ROOT / "src" / "lantern" / "graph"


def _graph_trees() -> List[tuple]:
    """`(relative_path, parsed_tree)` for every `.py` file under
    `src/lantern/graph/`."""
    return [
        (path.relative_to(PROJECT_ROOT).as_posix(), ast.parse(path.read_text("utf-8")))
        for path in sorted(GRAPH_DIR.rglob("*.py"))
    ]


def _factories_with_write_tool_param(tree: ast.AST) -> List[str]:
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and "call_write_tool" in {arg.arg for arg in node.args.args}
    ]


def _write_tool_call_sites(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "call_write_tool"
    )


def _function_source(name: str) -> str:
    func = getattr(nodes, name)
    return inspect.getsource(func)


def test_call_write_tool_is_a_parameter_of_exactly_one_node_factory() -> None:
    """`build_recovery_graph` (`build.py`) legitimately carries the
    parameter too -- it is the composition root that threads it INTO
    `make_write_and_readback_node`, not a second node factory. Every
    other function in the package must not."""
    factories: List[str] = []
    for _rel, tree in _graph_trees():
        factories.extend(_factories_with_write_tool_param(tree))
    allowed = {"build_recovery_graph", "make_write_and_readback_node"}
    assert set(factories) == allowed
    assert factories.count("make_write_and_readback_node") == 1
    assert factories.count("build_recovery_graph") == 1


def test_write_guard_node_factory_has_no_write_tool_parameter() -> None:
    source = _function_source("make_write_guard_node")
    tree = ast.parse(source)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)
    param_names = {arg.arg for arg in func_def.args.args}
    assert "call_write_tool" not in param_names


def test_call_write_tool_is_invoked_exactly_once_across_the_graph_package() -> None:
    total = sum(_write_tool_call_sites(tree) for _rel, tree in _graph_trees())
    assert total == 1


def test_synthetic_second_module_violation_is_detected() -> None:
    """Proves the widened, whole-package scan actually catches a SECOND
    write call site added in a module OTHER than `nodes.py` -- the exact
    shape a careless refactor of D-G8-11's split could introduce with
    every scan limited to `nodes.py` alone staying green."""
    real_trees = _graph_trees()
    synthetic_source = (
        "def make_a_second_write_node(call_write_tool):\n"
        "    def node(state):\n"
        "        return call_write_tool('some_tool', {})\n"
        "    return node\n"
    )
    all_trees = real_trees + [("synthetic_module.py", ast.parse(synthetic_source))]

    factories: List[str] = []
    total_calls = 0
    for _rel, tree in all_trees:
        factories.extend(_factories_with_write_tool_param(tree))
        total_calls += _write_tool_call_sites(tree)

    assert "make_a_second_write_node" in factories
    assert total_calls != 1
