#!/usr/bin/env python3
"""instrux: an assembler-like language with Pythonic syntax.

Major capabilities:
- Explicit low-level opcodes and labels.
- Python-style indentation blocks (`if/else`, `while`, `for`, `repeat`, `def`).
- Safe expression engine (AST-based, no eval).
- Stack + memory + call stack VM.
- CLI options for debug tracing, bytecode dump, and REPL mode.
"""

from __future__ import annotations

import argparse
import ast
import operator
import re
import shlex
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union


class InstruxError(Exception):
    """Base class for Instrux errors."""


class ParseError(InstruxError):
    """Parsing/compilation error."""


class RuntimeInstruxError(InstruxError):
    """VM runtime error."""


Value = Union[int, str]


@dataclass(frozen=True)
class Instruction:
    op: str
    args: Tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"{self.op} {', '.join(self.args)}".rstrip()


class SafeExpression:
    """Safe evaluator for arithmetic/comparison/boolean expressions."""

    _bin_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: lambda a, b: int(a / b),
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.BitAnd: operator.and_,
        ast.BitOr: operator.or_,
        ast.BitXor: operator.xor,
        ast.LShift: operator.lshift,
        ast.RShift: operator.rshift,
    }

    _unary_ops = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Not: lambda x: int(not bool(x)),
        ast.Invert: operator.invert,
    }

    _cmp_ops = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
    }

    _allowed_funcs = {
        "abs": abs,
        "min": min,
        "max": max,
        "int": int,
        "bool": bool,
        "str": str,
        "len": len,
        "ord": ord,
        "chr": chr,
    }

    @staticmethod
    def _coerce_bool(v: Value) -> int:
        return int(bool(v))

    @staticmethod
    def _ensure_index(v: Value, fn_name: str) -> int:
        if not isinstance(v, int):
            raise RuntimeInstruxError(f"Function '{fn_name}' expects integer arguments")
        return v

    @classmethod
    def _safe_call(cls, func_name: str, args: List[Value]) -> Value:
        if func_name == "len":
            if len(args) != 1 or not isinstance(args[0], str):
                raise RuntimeInstruxError("Function 'len' expects exactly one string argument")
            return len(args[0])
        if func_name == "ord":
            if len(args) != 1 or not isinstance(args[0], str) or len(args[0]) != 1:
                raise RuntimeInstruxError("Function 'ord' expects exactly one single-character string")
            return ord(args[0])
        if func_name == "chr":
            if len(args) != 1:
                raise RuntimeInstruxError("Function 'chr' expects exactly one integer argument")
            return chr(cls._ensure_index(args[0], "chr"))
        if func_name in {"abs", "int", "bool"}:
            if any(isinstance(a, str) for a in args):
                raise RuntimeInstruxError(f"Function '{func_name}' expects numeric arguments")
        result = cls._allowed_funcs[func_name](*args)
        return int(result) if isinstance(result, bool) else result

    @classmethod
    def evaluate(cls, expr: str, names: Dict[str, Value]) -> Value:
        try:
            node = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise RuntimeInstruxError(f"Invalid expression '{expr}': {exc}") from exc
        return cls._eval_node(node.body, names)

    @classmethod
    def _eval_node(cls, node: ast.AST, names: Dict[str, Value]) -> Value:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, str, bool)):
                return int(node.value) if isinstance(node.value, bool) else node.value
            raise RuntimeInstruxError(f"Unsupported literal: {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise RuntimeInstruxError(f"Unknown variable '{node.id}'")

        if isinstance(node, ast.BinOp) and type(node.op) in cls._bin_ops:
            left = cls._eval_node(node.left, names)
            right = cls._eval_node(node.right, names)
            op_t = type(node.op)
            if op_t is ast.Add:
                if isinstance(left, int) and isinstance(right, int):
                    return left + right
                if isinstance(left, str) and isinstance(right, str):
                    return left + right
                raise RuntimeInstruxError("'+' requires both integers or both strings")
            if op_t is ast.Mult:
                if isinstance(left, int) and isinstance(right, int):
                    return left * right
                if isinstance(left, str) and isinstance(right, int):
                    return left * right
                if isinstance(left, int) and isinstance(right, str):
                    return left * right
                raise RuntimeInstruxError("'*' supports int*int or string repetition")
            if not isinstance(left, int) or not isinstance(right, int):
                raise RuntimeInstruxError("Binary operations require integers")
            return cls._bin_ops[op_t](left, right)

        if isinstance(node, ast.UnaryOp) and type(node.op) in cls._unary_ops:
            value = cls._eval_node(node.operand, names)
            if not isinstance(value, int):
                raise RuntimeInstruxError("Unary operations require integer operands")
            return cls._unary_ops[type(node.op)](value)

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = 1
                for v in node.values:
                    result = cls._coerce_bool(cls._eval_node(v, names))
                    if not result:
                        break
                return result
            if isinstance(node.op, ast.Or):
                result = 0
                for v in node.values:
                    result = cls._coerce_bool(cls._eval_node(v, names))
                    if result:
                        break
                return result

        if isinstance(node, ast.Compare):
            left = cls._eval_node(node.left, names)
            for op, comparator in zip(node.ops, node.comparators):
                if type(op) not in cls._cmp_ops:
                    raise RuntimeInstruxError("Unsupported comparison operator")
                right = cls._eval_node(comparator, names)
                if not cls._cmp_ops[type(op)](left, right):
                    return 0
                left = right
            return 1

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in cls._allowed_funcs:
                raise RuntimeInstruxError(f"Function '{func_name}' not allowed in expressions")
            args = [cls._eval_node(arg, names) for arg in node.args]
            return cls._safe_call(func_name, args)

        raise RuntimeInstruxError(f"Unsupported expression syntax: {ast.dump(node)}")


@dataclass
class ControlNode:
    kind: str
    header: str
    body: List[object]
    else_body: Optional[List[object]] = None
    elif_nodes: Optional[List["ControlNode"]] = None
    line_no: int = 0


class Parser:
    """Parses indentation-based source into flat VM instructions."""

    def __init__(self, source: str) -> None:
        self.lines = source.splitlines()
        self.instructions: List[Instruction] = []
        self._label_counter = 0

    def parse(self) -> List[Instruction]:
        tree, idx = self._parse_block(0, 0)
        if idx != len(self.lines):
            raise ParseError("Parser stopped early")
        # Jump over function bodies by default.
        fn_defs = [n for n in tree if isinstance(n, ControlNode) and n.kind == "def"]
        if fn_defs:
            self.instructions.append(Instruction("JMP", ("__entry",)))
            for node in tree:
                if isinstance(node, ControlNode) and node.kind == "def":
                    self._compile_node(node)
            self.instructions.append(Instruction("LABEL", ("__entry",)))
            for node in tree:
                if not (isinstance(node, ControlNode) and node.kind == "def"):
                    self._compile_node(node)
        else:
            for node in tree:
                self._compile_node(node)
        return self.instructions

    def _new_label(self, prefix: str) -> str:
        self._label_counter += 1
        return f"__{prefix}_{self._label_counter}"

    def _normalize(self, raw: str) -> str:
        return raw.split("#", 1)[0].rstrip()

    def _indent(self, raw: str, line_no: int) -> int:
        if "\t" in raw:
            raise ParseError(f"Line {line_no}: tabs are not supported")
        return len(raw) - len(raw.lstrip(" "))

    def _parse_block(self, start: int, base_indent: int) -> Tuple[List[object], int]:
        block: List[object] = []
        i = start
        while i < len(self.lines):
            raw = self.lines[i]
            line = self._normalize(raw)
            if not line:
                i += 1
                continue

            indent = self._indent(raw, i + 1)
            if indent < base_indent:
                break
            if indent > base_indent:
                raise ParseError(f"Line {i+1}: unexpected indentation")

            stripped = line.strip()
            if stripped == "else:":
                break

            if stripped.endswith(":"):
                header = stripped[:-1].strip()
                header_line_no = i + 1
                i += 1
                child_indent = self._next_child_indent(i, base_indent)
                child, i = self._parse_block(i, child_indent)

                else_body = None
                elif_nodes: List[ControlNode] = []
                probe = i
                while probe < len(self.lines):
                    maybe = self._normalize(self.lines[probe])
                    if not maybe:
                        probe += 1
                        continue
                    probe_indent = self._indent(self.lines[probe], probe + 1)
                    if probe_indent != base_indent:
                        break
                    stripped_maybe = maybe.strip()
                    if stripped_maybe.startswith("elif ") and stripped_maybe.endswith(":"):
                        elif_cond = stripped_maybe[len("elif ") : -1].strip()
                        elif_header = f"if {elif_cond}"
                        probe += 1
                        elif_indent = self._next_child_indent(probe, base_indent)
                        elif_body, i = self._parse_block(probe, elif_indent)
                        elif_nodes.append(
                            ControlNode(kind="if", header=elif_header, body=elif_body, line_no=probe + 1)
                        )
                        probe = i
                        continue
                    if stripped_maybe != "else:":
                        break
                    probe += 1
                    else_indent = self._next_child_indent(probe, base_indent)
                    else_body, i = self._parse_block(probe, else_indent)
                    break

                kind = self._header_kind(header, i)
                if kind == "if" and elif_nodes:
                    terminal_else = else_body
                    for elif_node in reversed(elif_nodes):
                        elif_node.else_body = terminal_else
                        terminal_else = [elif_node]
                    else_body = terminal_else
                block.append(
                    ControlNode(
                        kind=kind,
                        header=header,
                        body=child,
                        else_body=else_body,
                        elif_nodes=elif_nodes or None,
                        line_no=header_line_no,
                    )
                )
                continue

            block.append(("inst", stripped, i + 1))
            i += 1

        return block, i

    def _next_child_indent(self, start: int, base_indent: int) -> int:
        j = start
        while j < len(self.lines):
            line = self._normalize(self.lines[j])
            if not line:
                j += 1
                continue
            indent = self._indent(self.lines[j], j + 1)
            if indent <= base_indent:
                raise ParseError(f"Line {j+1}: expected an indented block")
            return indent
        raise ParseError("Unexpected end of file: missing block body")

    def _header_kind(self, header: str, line_no: int) -> str:
        for prefix in ("if ", "while ", "def ", "for ", "repeat "):
            if header.startswith(prefix):
                return prefix.strip()
        raise ParseError(f"Line {line_no}: unsupported block '{header}'")

    def _compile_node(self, node: object, loop_stack: Optional[List[Tuple[str, str]]] = None) -> None:
        if loop_stack is None:
            loop_stack = []

        if isinstance(node, tuple):
            _, line, line_no = node
            if line.lower() == "break":
                if not loop_stack:
                    raise ParseError(f"Line {line_no}: 'break' used outside of a loop")
                self.instructions.append(Instruction("JMP", (loop_stack[-1][1],)))
                return
            if line.lower() == "continue":
                if not loop_stack:
                    raise ParseError(f"Line {line_no}: 'continue' used outside of a loop")
                self.instructions.append(Instruction("JMP", (loop_stack[-1][0],)))
                return
            if line.lower() == "pass":
                self.instructions.append(Instruction("NOP", ()))
                return
            self.instructions.append(self._parse_instruction(line, line_no))
            return

        if not isinstance(node, ControlNode):
            raise ParseError("Internal parser error")

        if node.kind == "while":
            cond = node.header[len("while ") :].strip()
            start = self._new_label("while_start")
            end = self._new_label("while_end")
            self.instructions.extend(
                [Instruction("LABEL", (start,)), Instruction("EVAL", (cond,)), Instruction("JZ", (end,))]
            )
            for child in node.body:
                self._compile_node(child, loop_stack + [(start, end)])
            self.instructions.extend([Instruction("JMP", (start,)), Instruction("LABEL", (end,))])
            return

        if node.kind == "if":
            cond = node.header[len("if ") :].strip()
            else_label = self._new_label("if_else")
            end = self._new_label("if_end")
            self.instructions.extend([Instruction("EVAL", (cond,)), Instruction("JZ", (else_label,))])
            for child in node.body:
                self._compile_node(child, loop_stack)
            self.instructions.append(Instruction("JMP", (end,)))
            self.instructions.append(Instruction("LABEL", (else_label,)))
            for child in node.else_body or []:
                self._compile_node(child, loop_stack)
            self.instructions.append(Instruction("LABEL", (end,)))
            return

        if node.kind == "def":
            name = node.header[len("def ") :].strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ParseError(f"Invalid function name '{name}'")
            self.instructions.append(Instruction("LABEL", (name,)))
            for child in node.body:
                self._compile_node(child, loop_stack)
            if not self.instructions or self.instructions[-1].op != "RET":
                self.instructions.append(Instruction("RET", ()))
            return


        if node.kind == "repeat":
            count_expr = node.header[len("repeat ") :].strip()
            start = self._new_label("repeat_start")
            cont = self._new_label("repeat_continue")
            end = self._new_label("repeat_end")
            count_var = self._new_label("repeat_count")
            self.instructions.extend(
                [
                    Instruction("EVAL", (count_expr,)),
                    Instruction("STORE", (count_var,)),
                    Instruction("LABEL", (start,)),
                    Instruction("EVAL", (f"{count_var} > 0",)),
                    Instruction("JZ", (end,)),
                ]
            )
            for child in node.body:
                self._compile_node(child, loop_stack + [(cont, end)])
            self.instructions.extend(
                [
                    Instruction("LABEL", (cont,)),
                    Instruction("EVAL", (f"{count_var} - 1",)),
                    Instruction("STORE", (count_var,)),
                    Instruction("JMP", (start,)),
                    Instruction("LABEL", (end,)),
                ]
            )
            return
        if node.kind == "for":
            loop_var, start_expr, stop_expr, step_expr = self._parse_for_header(node.header, node.line_no)
            start = self._new_label("for_start")
            cont = self._new_label("for_continue")
            end = self._new_label("for_end")
            stop_var = self._new_label("for_stop")
            step_var = self._new_label("for_step")

            self.instructions.extend(
                [
                    Instruction("EVAL", (start_expr,)),
                    Instruction("STORE", (loop_var,)),
                    Instruction("EVAL", (stop_expr,)),
                    Instruction("STORE", (stop_var,)),
                    Instruction("EVAL", (step_expr,)),
                    Instruction("STORE", (step_var,)),
                    Instruction("EVAL", (f"{step_var} != 0",)),
                    Instruction("JZ", (end,)),
                    Instruction("LABEL", (start,)),
                    Instruction(
                        "EVAL",
                        (
                            f"(({step_var} > 0 and {loop_var} < {stop_var}) "
                            f"or ({step_var} < 0 and {loop_var} > {stop_var}))",
                        ),
                    ),
                    Instruction("JZ", (end,)),
                ]
            )
            for child in node.body:
                self._compile_node(child, loop_stack + [(cont, end)])
            self.instructions.extend(
                [
                    Instruction("LABEL", (cont,)),
                    Instruction("EVAL", (f"{loop_var} + {step_var}",)),
                    Instruction("STORE", (loop_var,)),
                    Instruction("JMP", (start,)),
                    Instruction("LABEL", (end,)),
                ]
            )
            return

    def _parse_for_header(self, header: str, line_no: int) -> Tuple[str, str, str, str]:
        m = re.fullmatch(r"for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+)", header)
        if not m:
            raise ParseError(f"Line {line_no}: invalid for-loop header")
        name, iterable_expr = m.groups()
        try:
            iterable_ast = ast.parse(iterable_expr, mode="eval").body
        except SyntaxError as exc:
            raise ParseError(f"Line {line_no}: invalid for-loop iterable: {exc}") from exc
        if (
            not isinstance(iterable_ast, ast.Call)
            or not isinstance(iterable_ast.func, ast.Name)
            or iterable_ast.func.id != "range"
            or iterable_ast.keywords
        ):
            raise ParseError(f"Line {line_no}: for-loops currently require range(...)")
        arg_texts = [ast.unparse(a).strip() for a in iterable_ast.args]
        if len(arg_texts) == 1:
            return name, "0", arg_texts[0], "1"
        if len(arg_texts) == 2:
            return name, arg_texts[0], arg_texts[1], "1"
        if len(arg_texts) == 3:
            return name, arg_texts[0], arg_texts[1], arg_texts[2]
        raise ParseError(f"Line {line_no}: range(...) accepts 1 to 3 positional arguments")

    def _parse_instruction(self, line: str, line_no: int) -> Instruction:
        # Sugar: x <op>= expression
        aug_assign = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(\+=|-=|\*=|//=|%=)\s*(.+)$", line)
        if aug_assign:
            name, op, expr = aug_assign.groups()
            op_expr = {
                "+=": f"{name} + ({expr})",
                "-=": f"{name} - ({expr})",
                "*=": f"{name} * ({expr})",
                "//=": f"{name} // ({expr})",
                "%=": f"{name} % ({expr})",
            }[op]
            self.instructions.append(Instruction("EVAL", (op_expr,)))
            return Instruction("STORE", (name,))

        # Sugar: x = expression
        assign = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
        if assign:
            name = assign.group(1)
            expr = assign.group(2).strip()
            self.instructions.append(Instruction("EVAL", (expr,)))
            return Instruction("STORE", (name,))

        # Sugar: print(expr)
        m_print_expr = re.match(r"^print\((.+)\)$", line, flags=re.IGNORECASE)
        if m_print_expr:
            expr = m_print_expr.group(1).strip()
            self.instructions.append(Instruction("EVAL", (expr,)))
            return Instruction("PRINTS", ())

        # label declaration
        if line.endswith(":"):
            name = line[:-1].strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ParseError(f"Line {line_no}: invalid label '{name}'")
            return Instruction("LABEL", (name,))

        try:
            parts = shlex.split(line, posix=True)
        except ValueError as exc:
            raise ParseError(f"Line {line_no}: {exc}") from exc

        if not parts:
            raise ParseError(f"Line {line_no}: empty statement")

        op = parts[0].upper()
        tail = line[len(parts[0]) :].strip()
        args: Tuple[str, ...]
        if tail:
            args = tuple(a.strip() for a in re.split(r"\s*,\s*", tail) if a.strip())
        else:
            args = ()
        return Instruction(op, args)


class VM:
    """Instrux virtual machine."""

    def __init__(self, instructions: Sequence[Instruction], debug: bool = False) -> None:
        self.instructions = list(instructions)
        self.debug = debug
        self.pc = 0
        self.stack: List[Value] = []
        self.memory: Dict[str, Value] = {}
        self.call_stack: List[int] = []
        self.labels = self._index_labels()

    def _index_labels(self) -> Dict[str, int]:
        labels: Dict[str, int] = {}
        for i, inst in enumerate(self.instructions):
            if inst.op == "LABEL":
                labels[inst.args[0]] = i
        return labels

    def _resolve(self, token: str) -> Value:
        token = token.strip()
        if token in self.memory:
            return self.memory[token]
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            return token[1:-1]
        raise RuntimeInstruxError(f"Unknown value '{token}'")

    def _int(self, v: Value, context: str) -> int:
        if not isinstance(v, int):
            raise RuntimeInstruxError(f"{context} expects integer values")
        return v

    def _binary_int(self, fn, name: str) -> None:
        if len(self.stack) < 2:
            raise RuntimeInstruxError(f"{name} requires 2 values on stack")
        b = self._int(self.stack.pop(), name)
        a = self._int(self.stack.pop(), name)
        self.stack.append(fn(a, b))

    def _jump(self, label: str) -> int:
        if label not in self.labels:
            raise RuntimeInstruxError(f"Unknown label '{label}'")
        return self.labels[label] + 1

    def dump(self) -> str:
        lines = []
        for i, inst in enumerate(self.instructions):
            lines.append(f"{i:04d}: {inst}")
        return "\n".join(lines)

    def run(self) -> None:
        while self.pc < len(self.instructions):
            inst = self.instructions[self.pc]
            op, args = inst.op, inst.args
            if self.debug:
                print(f"[pc={self.pc}] {inst} | stack={self.stack} mem={self.memory}", file=sys.stderr)

            if op == "LABEL":
                self.pc += 1
                continue

            if op == "HALT":
                break

            if op == "NOP":
                self.pc += 1
                continue

            if op == "MOV":
                if len(args) != 2:
                    raise RuntimeInstruxError("MOV expects: MOV name, value")
                name, token = args
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    raise RuntimeInstruxError(f"Invalid variable name '{name}'")
                self.memory[name] = self._resolve(token)
                self.pc += 1
                continue

            if op == "EVAL":
                if len(args) != 1:
                    raise RuntimeInstruxError("EVAL expects one expression")
                self.stack.append(SafeExpression.evaluate(args[0], self.memory))
                self.pc += 1
                continue

            if op == "PUSH":
                if len(args) != 1:
                    raise RuntimeInstruxError("PUSH expects one argument")
                self.stack.append(self._resolve(args[0]))
                self.pc += 1
                continue

            if op == "POP":
                if len(args) != 1:
                    raise RuntimeInstruxError("POP expects variable name")
                if not self.stack:
                    raise RuntimeInstruxError("POP on empty stack")
                self.memory[args[0]] = self.stack.pop()
                self.pc += 1
                continue

            if op == "LOAD":
                if len(args) != 1:
                    raise RuntimeInstruxError("LOAD expects variable name")
                if args[0] not in self.memory:
                    raise RuntimeInstruxError(f"Unknown variable '{args[0]}'")
                self.stack.append(self.memory[args[0]])
                self.pc += 1
                continue

            if op == "STORE":
                if len(args) != 1:
                    raise RuntimeInstruxError("STORE expects variable name")
                if not self.stack:
                    raise RuntimeInstruxError("STORE with empty stack")
                self.memory[args[0]] = self.stack.pop()
                self.pc += 1
                continue

            if op == "DUP":
                if not self.stack:
                    raise RuntimeInstruxError("DUP on empty stack")
                self.stack.append(self.stack[-1])
                self.pc += 1
                continue

            if op == "DROP":
                if not self.stack:
                    raise RuntimeInstruxError("DROP on empty stack")
                self.stack.pop()
                self.pc += 1
                continue

            if op == "SWAP":
                if len(self.stack) < 2:
                    raise RuntimeInstruxError("SWAP requires 2 stack values")
                self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]
                self.pc += 1
                continue

            if op == "ADD":
                self._binary_int(lambda a, b: a + b, "ADD")
                self.pc += 1
                continue
            if op == "SUB":
                self._binary_int(lambda a, b: a - b, "SUB")
                self.pc += 1
                continue
            if op == "MUL":
                self._binary_int(lambda a, b: a * b, "MUL")
                self.pc += 1
                continue
            if op == "DIV":
                self._binary_int(lambda a, b: int(a / b), "DIV")
                self.pc += 1
                continue
            if op == "MOD":
                self._binary_int(lambda a, b: a % b, "MOD")
                self.pc += 1
                continue

            if op == "CMP":
                if len(args) != 2:
                    raise RuntimeInstruxError("CMP expects: CMP left, right")
                self.stack.append(1 if self._resolve(args[0]) == self._resolve(args[1]) else 0)
                self.pc += 1
                continue

            if op == "JMP":
                if len(args) != 1:
                    raise RuntimeInstruxError("JMP expects label")
                self.pc = self._jump(args[0])
                continue

            if op == "JZ":
                if len(args) != 1:
                    raise RuntimeInstruxError("JZ expects label")
                if not self.stack:
                    raise RuntimeInstruxError("JZ needs condition on stack")
                cond = self._int(self.stack.pop(), "JZ")
                self.pc = self._jump(args[0]) if cond == 0 else self.pc + 1
                continue

            if op == "JNZ":
                if len(args) != 1:
                    raise RuntimeInstruxError("JNZ expects label")
                if not self.stack:
                    raise RuntimeInstruxError("JNZ needs condition on stack")
                cond = self._int(self.stack.pop(), "JNZ")
                self.pc = self._jump(args[0]) if cond != 0 else self.pc + 1
                continue

            if op == "CALL":
                if len(args) != 1:
                    raise RuntimeInstruxError("CALL expects function/label name")
                self.call_stack.append(self.pc + 1)
                self.pc = self._jump(args[0])
                continue

            if op == "RET":
                if not self.call_stack:
                    # allow RET at top-level function bodies when directly jumped over
                    break
                self.pc = self.call_stack.pop()
                continue

            if op == "PRINT":
                if len(args) != 1:
                    raise RuntimeInstruxError("PRINT expects one argument")
                print(self._resolve(args[0]))
                self.pc += 1
                continue

            if op == "PRINTS":
                if not self.stack:
                    raise RuntimeInstruxError("PRINTS requires value on stack")
                print(self.stack.pop())
                self.pc += 1
                continue

            raise RuntimeInstruxError(f"Unknown opcode '{op}' at pc={self.pc}")


def compile_source(source: str) -> List[Instruction]:
    return Parser(source).parse()


def run_source(source: str, debug: bool = False, dump_bytecode: bool = False) -> VM:
    instructions = compile_source(source)
    vm = VM(instructions, debug=debug)
    if dump_bytecode:
        print(vm.dump())
    vm.run()
    return vm


def run_file(path: str, debug: bool = False, dump_bytecode: bool = False) -> VM:
    with open(path, "r", encoding="utf-8") as f:
        return run_source(f.read(), debug=debug, dump_bytecode=dump_bytecode)


def repl() -> int:
    print("Instrux REPL (type ':quit' to exit, ':run' to execute current buffer)")
    buffer: List[str] = []
    while True:
        try:
            line = input("ix> ")
        except EOFError:
            print()
            return 0
        cmd = line.strip()
        if cmd == ":quit":
            return 0
        if cmd == ":clear":
            buffer.clear()
            print("buffer cleared")
            continue
        if cmd == ":show":
            print("\n".join(buffer) if buffer else "<empty>")
            continue
        if cmd == ":run":
            try:
                run_source("\n".join(buffer))
            except InstruxError as exc:
                print(f"error: {exc}")
            continue
        buffer.append(line)


def _cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Instrux VM")
    p.add_argument("file", nargs="?", help="Path to .ix source file")
    p.add_argument("--debug", action="store_true", help="Print VM trace")
    p.add_argument("--dump-bytecode", action="store_true", help="Dump compiled instruction stream")
    p.add_argument("--repl", action="store_true", help="Run interactive REPL")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _cli().parse_args(argv)
    if args.repl:
        return repl()
    if not args.file:
        print("error: provide a source file or use --repl", file=sys.stderr)
        return 2
    try:
        run_file(args.file, debug=args.debug, dump_bytecode=args.dump_bytecode)
        return 0
    except InstruxError as exc:
        print(f"instrux error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
