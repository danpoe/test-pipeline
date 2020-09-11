import re
import resource
import psutil
import subprocess
import tempfile
import threading
import time


class FalsePass:
  def __init__(self):
    pass
  def __call__(self, f):
    return False


class MeasureMemoryUsage(threading.Thread):
  '''Measures memory usage of a given process'''

  def __init__(self, process, step=0.1, include_children=True):
    super(MeasureMemoryUsage, self).__init__()
    self.process = process
    self.step = step
    self.include_children = include_children
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
        if self.include_children:
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
    # TODO: adjust time handling
    #utime = res.ru_utime - _utime_sum
    #stime = res.ru_stime - _stime_sum
    utime = res.ru_utime - 0
    stime = res.ru_stime - 0
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