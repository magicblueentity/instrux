import io
import unittest
from contextlib import redirect_stdout

from instrux import compile_source, run_source


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


if __name__ == "__main__":
    unittest.main()
