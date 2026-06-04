"""Condition node: evaluates a safe expression on upstream output."""

from __future__ import annotations

import ast
import json
import operator
from typing import Any

from hestia.app import AppContext
from hestia.workflows.models import WorkflowNode


class ConditionNode:
    """Evaluates an expression against resolved inputs."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Evaluate the configured expression.

        Args:
            app: Application context.
            node: The workflow node.
            inputs: Resolved inputs for this node.

        Returns:
            The result of the expression evaluation.

        Raises:
            ValueError: If ``expression`` is missing or invalid.
        """
        expression = node.config.get("expression")
        if expression is None:
            raise ValueError("ConditionNode requires 'expression' in config")

        inputs = json.loads(json.dumps(inputs, default=str))
        return _safe_eval(expression, inputs)


_COMPARISON_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
}

_BOOL_OPS: dict[type[ast.boolop], Any] = {
    ast.And: all,
    ast.Or: any,
}

_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}


def _safe_eval(expression: str, variables: dict[str, Any]) -> Any:
    """Safely evaluate a simple expression.

    Supports literals, variable lookups, comparisons, boolean operations,
    arithmetic, and attribute/item access.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {exc}") from exc

    return _eval_node(tree.body, variables)


def _eval_node(node: ast.AST, variables: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise NameError(f"Variable not found: {node.id}")
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, variables) for v in node.values]
        op = _BOOL_OPS.get(type(node.op))
        if op is None:
            raise ValueError(
                f"Unsupported boolean operator: {type(node.op).__name__}"
            )
        return op(values)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, variables)
        result = True
        for op_node, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval_node(comparator, variables)
            op = _COMPARISON_OPS.get(type(op_node))
            if op is None:
                raise ValueError(
                    f"Unsupported comparison: {type(op_node).__name__}"
                )
            result = result and op(left, right)
            left = right
        return result
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, variables)
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(
                f"Unsupported unary operator: {type(node.op).__name__}"
            )
        return op(operand)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(
                f"Unsupported binary operator: {type(node.op).__name__}"
            )
        return op(left, right)
    if isinstance(node, ast.Attribute):
        obj = _eval_node(node.value, variables)
        if node.attr.startswith("_"):
            raise ValueError(f"Access to private attribute {node.attr!r} is not allowed")
        return getattr(obj, node.attr)
    if isinstance(node, ast.Subscript):
        obj = _eval_node(node.value, variables)
        if node.slice is None:
            raise ValueError("Subscript with no slice")
        index = _eval_node(node.slice, variables)
        return obj[index]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, variables) for elt in node.elts)
    if isinstance(node, ast.List):
        return [_eval_node(elt, variables) for elt in node.elts]
    if isinstance(node, ast.Dict):
        dict_result: dict[Any, Any] = {}
        for k, v in zip(node.keys, node.values, strict=True):
            if k is None:
                raise ValueError("Dict unpacking is not supported")
            dict_result[_eval_node(k, variables)] = _eval_node(v, variables)
        return dict_result
    raise ValueError(f"Unsupported expression: {type(node).__name__}")
