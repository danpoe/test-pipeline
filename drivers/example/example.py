#!/usr/bin/env python3

'''
Template that illustrates how to benchmark a tool using the test pipeline

Usage:
./example [--input-file <file>]
'''

import test_pipeline
import analysis_passes

def _main():
  tp = test_pipeline.TestPipeline()
  tp.setup()

  # Check property 1
  cmd = ['echo', '--arg']
  p = analysis_passes.CheckPass(cmd, retcode=lambda r: r == 0)
  tp.add_pass(p)

  # Check property 2
  cmd = ['echo' , '--arg']
  p = analysis_passes.CheckPass(cmd, regex_stdout=r'example')
  tp.add_pass(p)

  # Run analysis
  cmd = ['echo', '--arg1', '--arg2']
  p = analysis_passes.RunPass(cmd, timeout=1800)
  tp.add_pass(p)

  tp.test()


if __name__ == '__main__':
  _main()