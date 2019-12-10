import run_tests as rt
import tempfile
import unittest

class Test(unittest.TestCase):
  def test_run_pass_basic(self):
    p = rt.RunPass(['echo', 'test'], ignore_file=True)
    with tempfile.TemporaryFile('w') as f1,\
      tempfile.TemporaryFile('w') as f2,\
      tempfile.TemporaryFile('w') as f3:
      p('ignored', [f1, f2, f3])

    