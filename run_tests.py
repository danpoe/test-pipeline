#!/usr/bin/env python3

# Test runner

import re
import subprocess

class CheckPass:
  def __init__(
    self,
    cmd,
    regex_stdout=None,
    regex_stderr=None,
    retcode=lambda r: True,
    check_stdout=lambda r: True,
    check_stderr=lambda r: True,
    timeout=None):

    self.cmd = cmd[:]
    self.regex_stdout = regex_stdout
    self.regex_stderr = regex_stderr
    self.timeout = timeout
    self.retcode = retcode
    self.check_stdout = check_stdout
    self.check_stderr = check_stderr

  def __call__(self, f):
    cmd = self.cmd[:]
    cmd.append(f)

    try:
      cp = subprocess.run(cmd, capture_output=True, text=True,
        timeout=self.timeout)
    except subprocess.TimeoutExpired:
      raise
    except subprocess.SubprocessError:
      raise

    if not self.retcode(cp.returncode):
      return False

    if self.regex_stdout:
      if not re.search(self.regex_stdout, cp.stdout):
        return False

    if self.regex_stderr:
      if not re.search(self.regex_stderr, cp.stderr):
        return False

    if not self.check_stdout(cp.stdout):
      return False

    if not self.check_stderr(cp.stderr):
      return False

    return True
