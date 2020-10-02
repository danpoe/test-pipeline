import test_passes
import subprocess
import unittest

class Test(unittest.TestCase):
  def test_check_pass_success(self):
    p = test_passes.CheckPass(
      ['echo'],
      regex_stdout=r'file',
      retcode=lambda r: r == 0,
      check_stdout=lambda s: s == 'file\n')
    r = p('file')
    self.assertTrue(r)

  def test_check_pass_failure(self):
    p = test_passes.CheckPass(
      ['echo'],
      retcode=lambda r: r == 1)
    r = p('file')
    self.assertFalse(r)

  def test_check_pass_timeout(self):
    p = test_passes.CheckPass(['sleep'], timeout=0.1)
    with self.assertRaises(subprocess.TimeoutExpired):
      p('1')
