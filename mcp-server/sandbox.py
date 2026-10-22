# -*- coding: utf-8 -*-
"""Restricted Python sandbox for financial-analysis.

The model writes Python (not JS) because this project is Python.
Allowed: literals, arithmetic, collections, comprehensions, simple functions.
Forbidden: import, attribute names starting with _, file/network/os access.
"""
from __future__ import annotations

import ast
import math
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta
from typing import Any

from settings import SANDBOX_TIMEOUT_SEC

ALLOWED_NODES = (
    ast.Module,
    ast.Expression,
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Del,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.If,
    ast.IfExp,
    ast.For,
    ast.While,
    ast.Break,
    ast.Continue,
    ast.Pass,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.And,
    ast.Or,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.BitAnd,
    ast.MatMult,
    ast.Not,
    ast.Invert,
    ast.UAdd,
    ast.USub,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    ast.Call,
    ast.keyword,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    ast.Return,
    ast.FunctionDef,
    ast.Lambda,
    ast.arguments,
    ast.arg,
    ast.Expr,
    ast.FormattedValue,
    ast.JoinedStr,
    ast.Try,
    ast.ExceptHandler,
    ast.Raise,
)
if hasattr(ast, "Match"):
    ALLOWED_NODES = ALLOWED_NODES + (ast.Match, ast.match_case, ast.MatchValue, ast.MatchAs)


FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "classmethod",
    "staticmethod",
    "type",
    "input",
    "help",
    "memoryview",
    "breakpoint",
}


def to_number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_print(*args: Any, **kwargs: Any) -> None:
    return None


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    "print": _safe_print,
    "Exception": Exception,
    "BaseException": BaseException,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "AttributeError": AttributeError,
    "NameError": NameError,
    "StopIteration": StopIteration,
}


class SandboxError(ValueError):
    pass


class _Guard(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> Any:
        if not isinstance(node, ALLOWED_NODES):
            raise SandboxError(f"沙箱禁止语法: {type(node).__name__}")
        return super().visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise SandboxError("沙箱禁止访问下划线属性")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_") or node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"沙箱禁止名称: {node.id}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("_"):
            raise SandboxError("沙箱禁止定义下划线函数")
        self.generic_visit(node)


def execute_financial_analysis(
    code: str,
    context: dict[str, Any] | None = None,
    datasets: dict[str, Any] | None = None,
    timeout_sec: float | None = None,
) -> Any:
    if not code or not str(code).strip():
        raise SandboxError("code 不能为空")
    tree = ast.parse(code, mode="exec")
    _Guard().visit(tree)
    compiled = compile(tree, "<financial_analysis>", "exec")

    env: dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
    env.update(
        {
            "math": math,
            "statistics": statistics,
            "Counter": Counter,
            "defaultdict": defaultdict,
            "datetime": datetime,
            "timedelta": timedelta,
            "to_number": to_number,
            "context": context or {},
            "datasets": datasets or {},
            "records": [],
            "result": None,
        }
    )
    if context:
        for key, value in context.items():
            if key.isidentifier() and not key.startswith("_"):
                env[key] = value
    if datasets:
        if len(datasets) == 1:
            env["records"] = next(iter(datasets.values()))
        else:
            merged: list[Any] = []
            for value in datasets.values():
                if isinstance(value, list):
                    merged.extend(value)
            if merged:
                env["records"] = merged
        for key, value in datasets.items():
            if key.isidentifier() and not key.startswith("_"):
                env[key] = value

    def _run() -> Any:
        exec(compiled, env, env)  # noqa: S102  controlled sandbox
        if env.get("result") is not None:
            return env["result"]
        return {k: env[k] for k in ("count", "summary", "data") if k in env and env[k] is not None}

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_run)
        try:
            return fut.result(timeout=timeout_sec or SANDBOX_TIMEOUT_SEC)
        except FuturesTimeout as exc:
            raise SandboxError(f"统计分析超时（>{timeout_sec or SANDBOX_TIMEOUT_SEC}s）") from exc
