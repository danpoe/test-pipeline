#!/usr/bin/env python3

# Test runner

import psutil
import re
import resource
import subprocess
import tempfile
import time

# Sum of previous measurements
_utime_sum = 0
_stime_sum = 0

class RunPass:
  def __init__(self, cmd, prefix='', timeout=None, ignore_file=False, add=None):
    self.cmd = cmd[:]
    self.prefix = prefix
    self.timeout = timeout
    self.ignore_file = ignore_file

    assert add == None or \
      (type(add) is str or (type(add) is list and len(add) == 2))
    self.add = add

    self.output = []
    s = 'run_pass'
    if prefix:
      s = prefix + '.' + s
    self.output.append(f'{s}.stdout')
    self.output.append(f'{s}.stderr')
    self.output.append(f'{s}.data')

  def __call__(self, f, output_files):
    global _utime_sum
    global _stime_sum

    stdout = output_files[0]
    stderr = output_files[1]
    data = output_files[2]

    cmd = self.cmd[:]

    if type(self.add) is list:
      cmd.append(self.add[0])
      cmd.append(f + self.add[1])

    if not self.ignore_file:
      cmd.append(f)

    if type(self.add) is str:
      cmd.append(f + self.add)

    tf_stdout = tempfile.TemporaryFile(mode='w+')
    tf_stderr = tempfile.TemporaryFile(mode='w+')

    timeout = False

    before = time.perf_counter()

    try:
      p = psutil.Popen(cmd, stdout=tf_stdout, stderr=tf_stderr)
    except OSError as oe:
      raise
    except ValueError as ve:
      raise

    try:
      try:
        r = p.wait(timeout=self.timeout)
      except psutil.TimeoutExpired:
        p.kill()
        r = p.wait()
        timeout = True
    except psutil.NoSuchProcess:
      raise
    except psutil.AccessDenied:
      raise

    after = time.perf_counter()

    diff = after - before
    assert diff >= 0

    tf_stdout.seek(0)
    for l in tf_stdout:
      stdout.write(l)

    tf_stderr.seek(0)
    for l in tf_stderr:
      stderr.write(l)

    tf_stdout.close()
    tf_stderr.close()

    res = resource.getrusage(resource.RUSAGE_CHILDREN)
    utime = res.ru_utime - _utime_sum
    stime = res.ru_stime - _stime_sum
    assert utime >= 0
    assert stime >= 0
    _utime_sum = res.ru_utime
    _stime_sum = res.ru_stime

    data.write(f'Timeout: {timeout}\n')
    data.write(f'User time: {utime}\n')
    data.write(f'Sys time: {stime}\n')
    data.write(f'Real time: {diff}\n')
    data.write(f'Exit code: {r}\n')

    return True

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
