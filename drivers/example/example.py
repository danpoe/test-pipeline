#!/usr/bin/env python3

'''
Template that illustrates how to benchmark a tool using the run tests framework

Usage:
./example [--input-file <file>]
'''

import run_tests as rt

def _main():
  rt.setup()

  # Check property 1
  cmd = ['echo', '--arg']
  p = rt.CheckPass(cmd, retcode=lambda r: r == 0)
  rt.add_pass(p)

  # Check property 2
  cmd = ['echo' , '--arg']
  p = rt.CheckPass(cmd, regex_stdout=r'example')
  rt.add_pass(p)

  # Run analysis
  cmd = ['echo', '--arg1', '--arg2']
  p = rt.RunPass(cmd, timeout=1800)
  rt.add_pass(p)

  rt.test()


if __name__ == '__main__':
  _main()