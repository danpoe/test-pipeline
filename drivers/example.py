#!/usr/bin/env python3

'''
Template that illustrates how to benchmark a tool using the run tests framework

Usage:
./example.py <input_file> <analysis_root> <output_root>

<input_file>: file that lists the objects to analyse
<analysis_root>: directory into which all objects are put before analysis
<output_root>: directory into which all analysis output files are put
'''

import run_tests as rt

def _main():
  rt.setup()

  # Check property 1
  cmd = ['check_cmd', '--arg']
  p = rt.CheckPass(cmd, retcode=lambda r: r == 0)
  rt.add_pass(p)

  # Check property 2
  cmd = ['check_cmd' , '--arg']
  p = rt.CheckPass(cmd, regex_stdout=r'example')
  rt.add_pass(p)

  # Run analysis
  cmd = ['cmd', '--arg1', '--arg2']
  p = rt.RunPass(cmd, timeout=1800)
  rt.add_pass(p)

  rt.test()


if __name__ == '__main__':
  _main()