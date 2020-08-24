#!/usr/bin/env python3

'''
Test running framework

The framework runs a number of custom analysis passes on a given set of files.
The files the passes are run on are specified in an input file. Before running
the analysis on a file, the file is copied to (a subdirectory of) the given
directory `analysis_root`, and output files are put into (a subdirectory of) the
given directory `output_root`.

The framework needs to be instantiated in a driver script, which configures and
adds the analysis passes to run. See `drivers/example/example.py` for an
example. Analysis passes are added via `add_pass()`, and are run in order on
each test file when `test()` is invoked. When an earlier analysis pass returns
`False`, the subsequent passes are not run. This allows to run passes only on
files with specific properties.

An analysis pass is a callable that gets the path to the file to analyse as an
argument. An optional second argument gives a list of files to write output to.
If an analysis pass produces output, it needs to declare the output filenames
via a member variable `output`, which is a list of filenames. For examples of
configurable passes see `RunPass` and `CheckPass` below.
'''

import argparse
import ast
import inspect
import os
import psutil
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import urllib.parse

# Config
_input_file = ''
_analysis_root = ''
_output_root = ''
_start_line = 0
_num_lines = 0
_include_children = True
_progress = True

_passes = []

# Constants
_archive_suf = '.tar.bz2'

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


def timed_out():
  now = time.time()
  if _timeout:
    return now - _starting_time > _timeout
  return False

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


def _split(line):
  l, s, r = line.partition(_archive_suf)
  if s:
    assert not r or (len(r) > 1 and r.startswith('/'))
    return l + s, r
  return '', l


def _join(*components):
  return os.path.normpath('/'.join(components))


def _expand_path(path):
  assert os.path.isabs(_input_file)

  dirname = os.path.dirname(_input_file)
  if path.startswith('^'):
    assert path.startswith('^/')
    path = dirname + path[1:]
    assert os.path.isabs(path)
    return path

  path = os.path.expanduser(path)
  path = os.path.abspath(path)
  return path


def _copy_and_merge(src, tgt):
  '''
  Copy source to target

  Copies the source file or folder to the target file or folder. Folders are
  merged, and entries are not overwritten.

  :param src: source file or folder
  :param tgt: target file or folder
  '''

  assert os.path.isabs(src)
  assert os.path.isabs(tgt)
  assert os.path.exists(src)

  if os.path.isfile(src):
    if not os.path.exists(tgt):
      dirname = os.path.dirname(tgt)
      os.makedirs(dirname, exist_ok=True)
      shutil.copy2(src, tgt)
    return

  assert os.path.isdir(src)

  if os.path.exists(tgt):
    if os.path.isfile(tgt):
      return

    entries = [(os.path.join(src, entry), os.path.join(tgt, entry))
      for entry in os.listdir(src)]

    for entry_src, entry_tgt in entries:
      _copy_and_merge(entry_src, entry_tgt)

    return

  assert not os.path.exists(tgt)

  shutil.copytree(src, tgt)


def wrap_list(v):
  return v if type(v) is list else [v]


def unwrap_list(v):
  return v[0] if type(v) is list and len(v) == 1 else v


def validate_function(f):
  s = inspect.getsource(f)
  s = textwrap.dedent(s)
  tree = ast.parse(s)

  opens_file = False

  class CallValidator(ast.NodeVisitor):
    def visit_Call(self, call):
      nonlocal opens_file
      func = call.func
      if hasattr(func, 'id') and func.id == 'open':
        opens_file = True
      else:
        self.generic_visit(call)

  CallValidator().visit(tree)

  return not opens_file


def validate_pass(p):
  if hasattr(p, '__call__'):
    f = p.__call__
  else:
    f = p

  return validate_function(f)


def _handle_archive_entry():
  pass


def _indicates_url(r):
  return False


def _run_analysis(f, output_dir):
  assert os.path.isabs(f)
  assert os.path.isabs(output_dir)

  parent = os.path.dirname(f)
  assert os.path.isabs(parent)

  cwd = os.getcwd()
  os.chdir(parent)

  progress('Analysis passes: ', end='')

  for p in _passes:
    try:
      if hasattr(p, 'output'):
        output = wrap_list(p.output)

        fos = []
        for out in output:
          out = os.path.join(output_dir, out)
          fo = open(out, 'w')
          fos.append(fo)

        try:
          r = p(f, unwrap_list(fos))
        except KeyboardInterrupt:
          raise
        except BaseException as be:
          progress('!')
          traceback.print_exc(file=sys.stdout)
          break
        finally:
          for fo in fos:
            fo.close()
      else:
        try:
          r = p(f)
        except KeyboardInterrupt:
          raise
        except BaseException as be:
          progress('!')
          traceback.print_exc(file=sys.stdout)
          break
    except KeyboardInterrupt:
      raise
    except BaseException as be:
      progress('^')
      traceback.print_exc(file=sys.stdout)
      break

    progress('#', end='')

    if not r:
      break

  progress()
  os.chdir(cwd)


def _handle_local_path(analysis_path, output_path):
  assert os.path.isabs(analysis_path)
  assert os.path.isabs(output_path)

  worklist = [(analysis_path, output_path)]

  while worklist:
    p1, p2 = worklist.pop()
    if os.path.isdir(p1):
      entries = os.listdir(p1)
      paths = [(os.path.join(p1, entry), os.path.join(p2, entry))
        for entry in entries]
      worklist.extend(paths)
    else:
      assert os.path.isfile(p1)

      if timed_out():
        raise TimeoutException()

      os.makedirs(p2, exist_ok=True)

      rp = os.path.relpath(p1, _analysis_root)
      progress('Analysing: ' + rp)

      _run_analysis(p1, p2)


def _handle_simple_entry(entry):
  r = urllib.parse.urlparse(entry)
  if _indicates_url(r):
    url = entry
    analysis_path = _join(_analysis_root, r.scheme, r.netloc, r.path)
    if not os.path.exists(analysis_path):
      dirname = os.path.dirname(analysis_path)
      os.makedirs(dirname, exist_ok=True)
      urllib.request.urlretrieve(url, analysis_path)
      assert not os.path.exists(analysis_path) or os.path.isfile(analysis_path)
    output_path = _join(_output_root, r.scheme, r.netloc, r.path)
  else:
    path = _expand_path(entry)
    analysis_path = _join(_analysis_root, path)
    _copy_and_merge(path, analysis_path)
    output_path = _join(_output_root, path)

  return analysis_path, output_path


def _handle_line(line):
  assert line
  pre, suf = _split(line)
  assert pre or suf

  if pre:
    analysis_path, output_path = _handle_archive_entry(pre, suf)
  else:
    analysis_path, output_path = _handle_simple_entry(suf)

  if os.path.exists(analysis_path):
    rp = os.path.relpath(analysis_path, _analysis_root)
    progress('Local path: ' + rp)
    _handle_local_path(analysis_path, output_path)


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
      fatal(f'Line {i + 1} in input is invalid')


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


def add_pass(p):
  '''Add an analysis pass to be run'''
  global _passes
  assert _setup_done

  assert validate_pass(p)
  _passes.append(p)


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
