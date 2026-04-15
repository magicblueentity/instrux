import io
import unittest
from contextlib import redirect_stdout

from instrux import ParseError, compile_source, run_source


class InstruxTests(unittest.TestCase):
    def run_and_capture(self, src: str):
        buf = io.StringIO()
        with redirect_stdout(buf):
            vm = run_source(src)
        return vm, buf.getvalue().strip().splitlines() if buf.getvalue().strip() else []

    def test_assignment_and_while(self):
        src = """
n = 3
while n > 0:
  print(n)
  n = n - 1
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["3", "2", "1"])

    def test_if_else(self):
        src = """
a = 10
if a < 5:
  print(1)
else:
  print(2)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["2"])

    def test_function_call(self):
        src = """
MOV n, 5
CALL dec
PRINT n
HALT

def dec:
  n = n - 1
  RET
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["4"])

    def test_compile_contains_jump_to_entry_for_defs(self):
        src = """
def f:
  RET
HALT
"""
        instructions = compile_source(src)
        self.assertEqual(instructions[0].op, "JMP")

    def test_elif_chain(self):
        src = """
x = 7
if x < 3:
  print(1)
elif x < 5:
  print(2)
elif x < 9:
  print(3)
else:
  print(4)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["3"])

    def test_break_and_continue(self):
        src = """
i = 0
while i < 6:
  i = i + 1
  if i % 2 == 0:
    continue
  if i > 4:
    break
  print(i)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["1", "3"])

    def test_break_outside_loop_errors(self):
        with self.assertRaises(ParseError):
            compile_source("break\nHALT\n")

    def test_for_loop_range_variants(self):
        src = """
sum_a = 0
for i in range(5):
  sum_a = sum_a + i
print(sum_a)

sum_b = 0
for i in range(2, 8, 2):
  sum_b = sum_b + i
print(sum_b)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["10", "12"])

    def test_for_loop_negative_step_and_continue(self):
        src = """
acc = 0
for i in range(5, -1, -1):
  if i % 2 == 0:
    continue
  acc = acc + i
print(acc)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["9"])

    def test_pass_statement(self):
        src = """
x = 3
if x > 0:
  pass
print(x)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["3"])

    def test_repeat_loop_and_augmented_assignment(self):
        src = """
acc = 1
repeat 4:
  acc += 2
print(acc)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["9"])

    def test_string_expression_features(self):
        src = """
name = "ix"
msg = name + "!" * 2
print(msg)
print(len(msg))
print(chr(ord("A") + 1))
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["ix!!", "4", "B"])

    def test_for_loop_zero_step_finishes_safely(self):
        src = """
for i in range(1, 5, 0):
  print(i)
print(99)
HALT
"""
        _, out = self.run_and_capture(src)
        self.assertEqual(out, ["99"])


if __name__ == "__main__":
    unittest.main()
