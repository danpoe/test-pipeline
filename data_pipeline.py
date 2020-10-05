import os
import csv
import sys


def fatal(msg):
  print(msg, file=sys.stderr)
  sys.exit(1)


class DataPipeline:
  def __init__(self):
    self._output_root = 'output_root'
    self._output_file = 'results.csv'

    self._passes = []

    self._setup_done = False

  def setup(self):
    '''Set up the data gathering framework and parse arguments'''
    global _output_root
    global _output_file
    global _setup_done

    _output_root = os.path.abspath(self._output_root)
    if not os.path.isdir(_output_root):
      fatal(f'Directory {_output_root} does not exist')

    _output_file = os.path.abspath(self._output_file)

    if os.path.exists(_output_file) and not os.access(_output_file, os.W_OK):
      fatal(f'Output file {_output_file} not writable')

    _setup_done = True


  def add_pass(self, p):
    '''Add a data gathering pass to be run'''
    assert _setup_done

    self._passes.append(p)


  def gather_data(self):
    '''Run all added data gathering passes'''
    assert _setup_done
    assert self._passes

    records = []

    worklist = [_output_root]

    file_counter = 0

    while worklist:
      d = worklist.pop()
      entries = [os.path.join(d, entry) for entry in os.listdir(d)]
      leaf = True
      for entry in entries:
        if os.path.isdir(entry):
          leaf = False
          worklist.append(entry)
      if leaf:
        file_counter += 1

        rp = os.path.relpath(d, _output_root)
        records.append([rp])
        record = records[-1]

        cwd = os.getcwd()
        assert os.path.isabs(d)
        os.chdir(d)

        complete_record = False

        for p in self._passes:
          gathers_data = hasattr(p, 'column')

          if complete_record:
            if gathers_data:
              record.append('-')
            continue

          filename = os.path.join(d, p.input_file)

          if os.path.exists(filename):
            with open(filename) as f:
              s = f.read()
            b, r = p(s)
            assert '\n' not in r
            if gathers_data:
              if not r:
                r = '-'
              record.append(r)
            if not b:
              complete_record = True
              continue
          elif gathers_data:
            record.append('-')

        os.chdir(cwd)

    with open(_output_file, 'w') as f:
      writer = csv.writer(f)
      if records:
        heading = ['test']
        for p in self._passes:
          if hasattr(p, 'column'):
            heading.append(p.column)
        writer.writerow(heading)
      for record in records:
        writer.writerow(record)
