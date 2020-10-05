#!/usr/bin/env python3

'''
Gather data in a csv table

Usage:
./example.py
'''

import data_pipeline
import data_passes

def _main():
  dp = data_pipeline.DataPipeline()
  dp.setup()
  p = data_passes.FalsePass('data.txt')
  dp.add_pass(p)
  dp.gather_data()


if __name__ == '__main__':
  _main()
