import run_tests as rt
import unittest

class Test(unittest.TestCase):
  def test_check_pass_success(self):
    p = rt.CheckPass(
      ['echo'],
      regex_stdout=r'file',
      retcode=lambda r: r == 0,
      check_stdout=lambda s: s == 'file\n')
    r = p('file')
    self.assertTrue(r)

  def test_check_pass_failure(self):
    p = rt.CheckPass(
      ['echo'],
      retcode=lambda r: r == 1)
    r = p('file')
    self.assertFalse(r)
