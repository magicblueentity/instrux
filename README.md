# instrux

`instrux` is a **low-level, assembler-like programming language with Python-like syntax**.

It gives you two ways to write code:

1. **Raw opcode style** (e.g., `MOV`, `PUSH`, `ADD`, `JMP`, `CALL`).
2. **Pythonic sugar** (`x = expr`, `print(expr)`, indentation blocks for `if/else`, `while`, and `def`).

---

## What’s improved

This version significantly expands the system:

- Safe AST-based expression evaluation (no Python `eval`).
- `if/else` blocks.
- `elif` branches.
- `def name:` function declarations compiled to labels.
- Auto entry-point jump so function bodies are not executed at startup.
- Loop controls: `break` and `continue`.
- Pythonic `for` loops via `range(...)` (supports start/stop/step).
- `pass` statements for no-op block placeholders.
- Stack ops: `DUP`, `SWAP`, `DROP`.
- CLI features: `--debug`, `--dump-bytecode`, and `--repl`.
- Built-in unit tests.

---

## Quick start

```bash
python3 instrux.py examples/fibonacci.ix
```

Run factorial example:

```bash
python3 instrux.py examples/factorial.ix
```

Inspect compiled bytecode:

```bash
python3 instrux.py --dump-bytecode examples/factorial.ix
```

Start a REPL:

```bash
python3 instrux.py --repl
```

---

## Syntax overview

### Pythonic assignment sugar

```ix
x = 10
y = x * 2 + 3
print(y)
```

### Pythonic control flow

```ix
n = 5
while n > 0:
  if n % 2 == 0:
    print(n)
  else:
    print(0)
  n = n - 1
```

### `elif`, `break`, and `continue`

```ix
i = 0
while i < 10:
  i = i + 1
  if i % 2 == 0:
    continue
  elif i > 7:
    break
  print(i)
```

### `for` loops and `pass`

```ix
total = 0
for i in range(1, 6):
  if i == 3:
    pass
  total = total + i
print(total)
```

### Function declarations

```ix
def hello:
  PRINT "hello"
  RET

CALL hello
HALT
```

### Raw stack style

```ix
PUSH 7
PUSH 5
ADD
PRINTS
HALT
```

---

## Core instructions

- Data/variables: `MOV`, `LOAD`, `STORE`, `PUSH`, `POP`.
- Stack helpers: `DUP`, `SWAP`, `DROP`.
- Arithmetic: `ADD`, `SUB`, `MUL`, `DIV`, `MOD`.
- Comparison helpers: `CMP`, plus expression comparisons through `EVAL`.
- Control flow: `JMP`, `JZ`, `JNZ`, labels (`name:`).
- Functions: `CALL`, `RET`, `def name:`.
- Pythonic loops: `while expr:`, `for x in range(...):`.
- Output: `PRINT value`, `PRINTS` (prints top of stack).
- Misc: `EVAL`, `HALT`, `NOP`.

---

## Testing

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

---

## Notes

- Indentation must use spaces (tabs are rejected).
- `print(expr)` compiles to `EVAL expr` + `PRINTS`.
- Assignment (`x = expr`) compiles to `EVAL expr` + `STORE x`.
