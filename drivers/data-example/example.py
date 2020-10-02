#!/usr/bin/env python3

'''
Gather data in a csv table

Usage:
./example.py
'''

import data_pipeline
import data_passes

def _main():
  p = data_passes.FalsePass()
  data_pipeline.add_pass(p)
  data_pipeline.gather_data()


if __name__ == '__main__':
  _main()