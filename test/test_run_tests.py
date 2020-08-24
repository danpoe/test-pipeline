import glob
import os
import run_tests as rt
import shutil
import unittest

class Test(unittest.TestCase):
  def test_scenario1(self):
    pass
  
  def tearDown(self):
    os.remove('input.txt')
    for file in glob.glob('*.test'):
      os.remove(file)
    shutil.rmtree('analysis_root')
    shutil.rmtree('output_root')
