import analysis_passes
import tempfile
import unittest

class Test(unittest.TestCase):
  def test_run_pass_basic(self):
    p = analysis_passes.RunPass(['echo', 'test'], ignore_file=True)

    with tempfile.TemporaryFile('w+') as f_stdout,\
      tempfile.TemporaryFile('w+') as f_stderr,\
      tempfile.TemporaryFile('w+') as f_data:

      p('ignored', [f_stdout, f_stderr, f_data])

      f_stdout.seek(0)
      s = f_stdout.read()
      self.assertEqual(s, 'test\n')

      f_stderr.seek(0)
      s = f_stderr.read()
      self.assertEqual(s, '')

      l = ['Timeout', 'User time', 'Sys time', 'Real time',
        'Maximum resident set size', 'Maximum virtual memory size', 'Exit code']
      f_data.seek(0)
      for i, line in enumerate(f_data):
        self.assertTrue(line.startswith(l[i]))
