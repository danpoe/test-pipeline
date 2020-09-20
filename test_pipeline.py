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
import re
import resource
import shutil
import sys
import textwrap
import time
import traceback
import urllib.parse


def fatal(msg):
  print(msg, file=sys.stderr)
  sys.exit(1)


class TimeoutException(Exception):
  pass


class TestPipeline:
  def __init__(
    self,
    input_file='input.txt',
    analysis_root='analysis_root',
    output_root='output_root',
    start_line=1,
    num_lines=sys.maxsize,
    include_children=True,
    progress=True,
    timeout=None,
    memory_limit=None):

    # Config
    self._input_file = input_file
    self._analysis_root = analysis_root
    self._output_root = output_root
    self._start_line = start_line
    self._num_lines = num_lines
    self._include_children = include_children
    self._progress = progress
    self._timeout = timeout
    self._memory_limit = memory_limit

    # Analysis passes to run
    self._passes = []

    # Constants
    self._archive_suf = '.tar.bz2'

    # Sum of previous measurements
    self._utime_sum = 0
    self._stime_sum = 0

    # Misc
    self._setup_done = False
    self._starting_time = None


  @staticmethod
  def get_argument_parser():
    '''Set up argument parser'''
    parser = argparse.ArgumentParser(description='Test pipeline')
    parser.add_argument('--input-file', default='input.txt')
    parser.add_argument('--analysis-root', default='analysis_root')
    parser.add_argument('--output-root', default='output_root')
    parser.add_argument('--memory-limit', type=int)
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--progress', action='store_true')
    parser.add_argument('--start-line', default=1, type=int)
    parser.add_argument('--num-lines', default=sys.maxsize, type=int)
    return parser


  @staticmethod
  def from_arguments(args=None):
    '''
    Create analysis framework and configure it via the commandline arguments
    '''

    if not args:
      parser = TestPipeline.get_argument_parser()
      args = parser.parse_args()

    return TestPipeline(
      input_file=args.input_file,
      analysis_root=args.analysis_root,
      output_root=args.output_root,
      start_line=args.start_line,
      num_lines=args.num_lines,
      include_children=args.include_children,
      progress=args.progress)


  def setup(self):
    archive_formats = shutil.get_archive_formats()
    archive_formats = list(map(lambda p: p[0], archive_formats))
    assert 'bztar' in archive_formats

    if self._memory_limit:
      resource.setrlimit(resource.RLIMIT_AS,
        (self._memory_limit, resource.RLIM_INFINITY))

    self._starting_time = time.time()

    self._input_file = os.path.abspath(self._input_file)
    self._analysis_root = os.path.abspath(self._analysis_root)
    self._output_root = os.path.abspath(self._output_root)

    self._setup_done = True


  def progress(self, msg='', end='\n'):
    if self._progress:
      print(msg, end=end, flush=True)


  def timed_out(self):
    now = time.time()
    if self._timeout:
      return now - self._starting_time > self._timeout
    return False


  def _split(self, line):
    l, s, r = line.partition(self._archive_suf)
    if s:
      assert not r or (len(r) > 1 and r.startswith('/'))
      return l + s, r
    return '', l


  def _join(self, *components):
    return os.path.normpath('/'.join(components))


  def _expand_path(self, path):
    assert os.path.isabs(self._input_file)

    dirname = os.path.dirname(self._input_file)
    if path.startswith('^'):
      assert path.startswith('^/')
      path = dirname + path[1:]
      assert os.path.isabs(path)
      return path

    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    return path


  def _copy_and_merge(self, src, tgt):
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
        self._copy_and_merge(entry_src, entry_tgt)

      return

    assert not os.path.exists(tgt)

    shutil.copytree(src, tgt)


  def wrap_list(self, v):
    return v if type(v) is list else [v]


  def unwrap_list(self, v):
    return v[0] if type(v) is list and len(v) == 1 else v


  def validate_function(self, f):
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


  def validate_pass(self, p):
    if hasattr(p, '__call__'):
      f = p.__call__
    else:
      f = p

    return self.validate_function(f)


  def _handle_archive_entry(self):
    pass


  def _indicates_url(self, r):
    b = r.scheme and r.netloc
    assert not b or r.path
    return b


  def _run_analysis(self, f, output_dir):
    assert os.path.isabs(f)
    assert os.path.isabs(output_dir)

    parent = os.path.dirname(f)
    assert os.path.isabs(parent)

    cwd = os.getcwd()
    os.chdir(parent)

    self.progress('Analysis passes: ', end='')

    for p in self._passes:
      try:
        if hasattr(p, 'output'):
          output = self.wrap_list(p.output)

          fos = []
          for out in output:
            out = os.path.join(output_dir, out)
            fo = open(out, 'w')
            fos.append(fo)

          try:
            r = p(f, self.unwrap_list(fos))
          except KeyboardInterrupt:
            raise
          except BaseException as be:
            self.progress('!')
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
            self.progress('!')
            traceback.print_exc(file=sys.stdout)
            break
      except KeyboardInterrupt:
        raise
      except BaseException as be:
        self.progress('^')
        traceback.print_exc(file=sys.stdout)
        break

      self.progress('#', end='')

      if not r:
        break

    self.progress()
    os.chdir(cwd)


  def _handle_local_path(self, analysis_path, output_path):
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

        if self.timed_out():
          raise TimeoutException()

        os.makedirs(p2, exist_ok=True)

        rp = os.path.relpath(p1, self._analysis_root)
        self.progress('Analysing: ' + rp)

        self._run_analysis(p1, p2)


  def _handle_simple_entry(self, entry):
    r = urllib.parse.urlparse(entry)
    if self._indicates_url(r):
      url = entry
      analysis_path = self._join(self._analysis_root, r.scheme, r.netloc, r.path)
      if not os.path.exists(analysis_path):
        dirname = os.path.dirname(analysis_path)
        os.makedirs(dirname, exist_ok=True)
        urllib.request.urlretrieve(url, analysis_path)
        assert not os.path.exists(analysis_path) or os.path.isfile(analysis_path)
      output_path = self._join(self._output_root, r.scheme, r.netloc, r.path)
    else:
      path = self._expand_path(entry)
      analysis_path = self._join(self._analysis_root, path)
      self._copy_and_merge(path, analysis_path)
      output_path = self._join(self._output_root, path)

    return analysis_path, output_path


  def _handle_line(self, line):
    assert line
    pre, suf = self._split(line)
    assert pre or suf

    if pre:
      analysis_path, output_path = self._handle_archive_entry(pre, suf)
    else:
      analysis_path, output_path = self._handle_simple_entry(suf)

    if os.path.exists(analysis_path):
      rp = os.path.relpath(analysis_path, self._analysis_root)
      self.progress('Local path: ' + rp)
      self._handle_local_path(analysis_path, output_path)


  def _is_http_url_entry(self, s):
    r = urllib.parse.urlparse(s)

    if r.scheme != 'http' or not r.netloc or not r.path:
      return False

    if s.endswith('/'):
      return False

    if re.search(r'/\s*/', s[len('http://'):]):
      return False

    return True


  def _is_path_entry(self, s):
    if re.search(r'/\s*/', s):
      return False

    if s.endswith('/'):
      return False

    if s.startswith('~'):
      return s.startswith('~/')

    if s.startswith('^'):
      return s.startswith('^/')

    return True


  def _is_valid_entry(self, line):
    if not line:
      return True

    if line.startswith('#'):
      return True

    l = re.findall(self._archive_suf, line)
    if len(l) > 1:
      return False

    return self._is_http_url_entry(line) or self._is_path_entry(line)


  def _validate_lines(self, lines):
    for i, line in enumerate(lines):
      if not self._is_valid_entry(line):
        fatal(f'Line {i + 1} in input is invalid')


  def add_pass(self, p):
    '''Add an analysis pass to be run'''
    assert self._setup_done

    assert self.validate_pass(p)
    self._passes.append(p)


  def test(self):
    '''Run all added analysis passes'''

    with open(self._input_file) as f:
      lines = list(map(lambda l: l.strip(), f))
    self._validate_lines(lines)

    n = 0

    for i in range(self._start_line, len(lines) + 1):
      if n >= self._num_lines:
        break
      line = lines[i-1]
      self.progress(f'Handling line: {i:<7}')
      if line.startswith('#') or not line:
        continue
      n += 1
      try:
        self._handle_line(line)
      except KeyboardInterrupt:
        raise
      except TimeoutException:
        traceback.print_exc(file=sys.stdout)
        raise
      except BaseException as be:
        traceback.print_exc(file=sys.stdout)
