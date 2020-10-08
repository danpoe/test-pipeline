'''
Data gathering framework

The framework gathers the data produced by a test pipeline driver script and
produces a csv results table.

The framework needs to be instantiated in a driver script, which configures and
adds a number of data gathering and checking passes to run (for an example see
`drivers/data-example/example.py`). Passes are added via `add_pass()`, and are
run on the output files produced by the test pipeline when `gather_data()` is
invoked. The directory that contains the output of the test running framework
can be specified via the argument `output_root`.

A data gathering or checking pass is a callable that gets the contents of a file
as an argument. The passes need to define the file to read via the member
variable `input_file`. A data gathering pass corresponds to a column in the csv
results table and needs to additionally define a member variable `column`. It
gives the name of the column that corresponds to the pass. Each call to a data
gathering pass produces one entry in the respective column.

Both data gathering and checking passes return a pair (bool, str). The first
column indicates whether to run subsequent passes, and the second component
gives the extracted data to write to the csv column. The second component is
ignored for checking passes (i.e., passes that do not have a `column` member
variable).

For examples of configurable passes see `CopyPass` and `ExtractPass` in the
data_passes module.
'''

import argparse
import csv
import os
import sys


def fatal(msg):
  print(msg, file=sys.stderr)
  sys.exit(1)


class DataPipeline:
  def __init__(
    self,
    output_root = 'output_root',
    output_file = 'results.csv',
    progress = False):
    self._output_root = output_root
    self._output_file = output_file
    self._progress = progress

    self._passes = []

    self._setup_done = False

  def progress(self, msg='', end='\n'):
    if self._progress:
      print(msg, end=end, flush=True)

  @staticmethod
  def get_argument_parser():
    parser = argparse.ArgumentParser(description='Data pipeline')
    parser.add_argument('--output-root', default='output_root')
    parser.add_argument('--output-file', default='results.csv')
    parser.add_argument('--progress', action='store_true')
    return parser

  @staticmethod
  def from_arguments(args=None):
    if not args:
      parser = DataPipeline.get_argument_parser()
      args = parser.parse_args()

    return DataPipeline(args.output_root, args.output_file, args.progress)

  def setup(self):
    '''Set up the data gathering framework and parse arguments'''

    _output_root = os.path.abspath(self._output_root)
    if not os.path.isdir(_output_root):
      fatal(f'Directory {_output_root} does not exist')

    _output_file = os.path.abspath(self._output_file)

    if os.path.exists(_output_file) and not os.access(_output_file, os.W_OK):
      fatal(f'Output file {_output_file} not writable')

    self._setup_done = True


  def add_pass(self, p):
    '''Add a data gathering pass to be run'''
    assert self._setup_done
    self._passes.append(p)


  def gather_data(self):
    '''Run all added data gathering passes'''
    assert self._setup_done
    assert self._passes

    records = []

    worklist = [self._output_root]

    self.progress('Starting exploration')
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

        rp = os.path.relpath(d, self._output_root)
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

    with open(self._output_file, 'w') as f:
      writer = csv.writer(f)
      if records:
        heading = ['test']
        for p in self._passes:
          if hasattr(p, 'column'):
            heading.append(p.column)
        writer.writerow(heading)
      for record in records:
        writer.writerow(record)
