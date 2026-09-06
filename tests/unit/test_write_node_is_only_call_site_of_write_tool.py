"""T16 (G5+G6 stage spec): the write-capable callable is referenced in
exactly one node function (`make_write_and_readback_node`), and is not a
parameter of the Write Guard node (`make_write_guard_node`) -- the guard
authorizes, it does not write (`CLAUDE.md` section 4).
"""

import ast
import inspect

from src.lantern.graph import nodes


def _function_source(name: str) -> str:
    func = getattr(nodes, name)
    return inspect.getsource(func)


def test_call_write_tool_is_a_parameter_of_exactly_one_node_factory() -> None:
    tree = ast.parse(inspect.getsource(nodes))
    factories_with_param = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            param_names = {arg.arg for arg in node.args.args}
            if "call_write_tool" in param_names:
                factories_with_param.append(node.name)

    assert factories_with_param == ["make_write_and_readback_node"]


def test_write_guard_node_factory_has_no_write_tool_parameter() -> None:
    source = _function_source("make_write_guard_node")
    tree = ast.parse(source)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)
    param_names = {arg.arg for arg in func_def.args.args}
    assert "call_write_tool" not in param_names


def test_call_write_tool_is_invoked_exactly_once_in_the_module() -> None:
    tree = ast.parse(inspect.getsource(nodes))
    call_sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "call_write_tool"
    ]
    assert len(call_sites) == 1
