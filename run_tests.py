#!/usr/bin/env python3

# Test runner

import argparse
import os
import psutil
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib

# Config
_input_file = ''
_analysis_root = ''
_output_root = ''
_start_line = 0
_num_lines = 0
_include_children = True
_progress = True

# Sum of previous measurements
_utime_sum = 0
_stime_sum = 0

# Misc
_setup_done = False
_starting_time = 0
_timeout = None


def fatal(msg):
  print(msg, file=sys.stderr)
  sys.exit(1)


def progress(msg='', end='\n'):
  if _progress:
    print(msg, end=end, flush=True)


class TimeoutException(Exception):
  pass


class MeasureMemoryUsage(threading.Thread):
  '''Measures memory usage of a given process'''

  def __init__(self, process, step=0.1):
    super(MeasureMemoryUsage, self).__init__()
    self.process = process
    self.step = step
    self.stop = threading.Event()
    self.max_rss = 0
    self.max_vms = 0

  def run(self):
    while not self.stop.is_set():
      rss = 0
      vms = 0
      try:
        m = self.process.memory_info()
        rss += m.rss
        vms += m.vms
        if _include_children:
          children = self.process.children(True)
          for c in children:
            m = c.memory_info()
            rss += m.rss
            vms += m.vms
      except psutil.NoSuchProcess:
        pass
      except psutil.AccessDenied:
        pass
      if rss > self.max_rss:
        self.max_rss = m.rss
      if vms > self.max_vms:
        self.max_vms = m.vms
      time.sleep(self.step)

  def join(self, timeout=None):
    self.stop.set()
    super(MeasureMemoryUsage, self).join(timeout)


class RunPass:
  '''Runs a given command and record performance metrics'''

  def __init__(
    self,
    cmd: list,
    prefix='',
    timeout=None,
    ignore_file=False,
    add=None):
    '''
    Create and configure the running pass

    :param cmd: Command to run, including arguments
    :param prefix: Prefix of filenames for created files
    :param timeout: Timeout for command
    :param ignore_file: If True, the filename passed to __call__() will be
        ignored
    :param add: File suffix to add to the filename passed to __call__()
    '''

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
      s = f'{prefix}.{s}'
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

    thread = MeasureMemoryUsage(p)
    thread.start()

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

    thread.join()

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
    data.write(f'Maximum resident set size: {thread.max_rss}\n')
    data.write(f'Maximum virtual memory size: {thread.max_vms}\n')
    data.write(f'Exit code: {r}\n')

    return True


class CheckPass:
  '''Runs a given command and verifies its return code and output'''

  def __init__(
    self,
    cmd : list,
    regex_stdout=None,
    regex_stderr=None,
    retcode=lambda r: True,
    check_stdout=lambda r: True,
    check_stderr=lambda r: True,
    timeout=None):
    '''
    Create and configure the checking pass

    The constructor takes several parameters which configure various checks that
    are performed on the return code and output of the command. The pass
    succeeds if all the checks succeed.

    :param cmd: Command to run, including arguments
    :param regex_stdout: Regex that must match the output written to stdout for
        the pass to succeed
    :param regex_stderr: Regex that must match the output written to stderr for
        the pass to succeed
    :param retcode: Function that will be applied to the return code of the
        command. The function must return True for the pass to succeed.
    :param check_stdout: Function that will be applied to the output written to
        stdout. The function must return True for the pass to succeed.
    :param check_stderr: Function that will be applied to the output written to
        stderr. The function must return True for the pass to succeed.
    :timeout: Timeout for the command
    '''

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


def _handle_line():
  pass


def _is_http_url_entry(s):
  r = urllib.parse.urlparse(s)

  if r.scheme != 'http' or not r.netloc or not r.path:
    return False

  if s.endswith('/'):
    return False

  if re.search(r'/\s*/', s[len('http://'):]):
    return False

  return True


def _is_path_entry(s):
  if re.search(r'/\s*/', s):
    return False

  if s.endswith('/'):
    return False

  if s.startswith('~'):
    return s.startswith('~/')

  if s.startswith('^'):
    return s.startswith('^/')

  return True


def _is_valid_entry(line):
  if not line:
    return True

  if line.startswith('#'):
    return True

  l = re.findall(_archive_suf, line)
  if len(l) > 1:
    return False

  return _is_http_url_entry(line) or _is_path_entry(line)


def _validate_lines(lines):
  for i, line in enumerate(lines):
    if not _is_valid_entry(line):
      fatal('Line ' + str(i + 1) + ' in input is invalid')


def setup_arg_parser():
  '''Set up argument parser'''
  parser = argparse.ArgumentParser(description='Run tests')
  parser.add_argument('--input-file', default='input.txt')
  parser.add_argument('--analysis-root', default='analysis_root')
  parser.add_argument('--output-root', default='output_root')
  parser.add_argument('--memory-limit', type=int)
  parser.add_argument('--timeout', type=int)
  parser.add_argument('--progress', action='store_true')
  parser.add_argument('--start', default=1, type=int)
  parser.add_argument('--num', default=sys.maxsize, type=int)
  return parser


def setup(parser=None):
  '''Set up the analysis framework and parse arguments'''
  global _input_file
  global _analysis_root
  global _output_root
  global _starting_time
  global _timeout
  global _progress
  global _start_line
  global _num_lines
  global _setup_done

  if not parser:
    parser = setup_arg_parser()

  args = parser.parse_args()

  archive_formats = shutil.get_archive_formats()
  archive_formats = list(map(lambda p: p[0], archive_formats))
  assert 'bztar' in archive_formats

  if args.memory_limit:
    resource.setrlimit(resource.RLIMIT_AS,
      (args.memory_limit, resource.RLIM_INFINITY))

  _starting_time = time.time()
  _timeout = args.timeout

  _input_file = os.path.abspath(args.input_file)
  _analysis_root = os.path.abspath(args.analysis_root)
  _output_root = os.path.abspath(args.output_root)

  _progress = args.progress
  _start_line = args.start
  _num_lines = args.num

  _setup_done = True

  return args


def test():
  '''Run all added analysis passes'''

  with open(_input_file) as f:
    lines = list(map(lambda l: l.strip(), f))
  _validate_lines(lines)

  n = 0

  for i in range(_start_line, len(lines) + 1):
    if n >= _num_lines:
      break
    line = lines[i-1]
    progress(f'Handling line: {i:<7}')
    if line.startswith('#') or not line:
      continue
    n += 1
    try:
      _handle_line(line)
    except KeyboardInterrupt:
      raise
    except TimeoutException:
      traceback.print_exc(file=sys.stdout)
      raise
    except BaseException as be:
      traceback.print_exc(file=sys.stdout)
