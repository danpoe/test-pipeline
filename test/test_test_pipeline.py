import glob
import os
import pathlib
import test_pipeline as tp
import shutil
import unittest

class Test(unittest.TestCase):
  def __init__(self):
    self._tp = tp.TestPipeline()

  @classmethod
  def setUpClass(cls):
    pathlib.Path('benchmark1.test').touch()
    pathlib.Path('benchmark2.test').touch()
    with open('input.txt', 'w') as f:
      f.write('benchmark1.test\n')
      f.write('benchmark2.test\n')

  def test_false(self):
    self._tp.setup()
    self._tp.add_pass(tp.FalsePass())
    self._tp.test()

    r = glob.glob('analysis_root/**/benchmark*.test', recursive=True)
    self.assertEqual(len(r), 2)
    self.assertTrue(os.path.isfile(r[0]))
    self.assertTrue(os.path.isfile(r[1]))

    r = glob.glob('output_root/**/benchmark*.test', recursive=True)
    self.assertEqual(len(r), 2)
    self.assertTrue(os.path.isdir(r[0]))
    self.assertTrue(os.path.isdir(r[1]))
    self.assertEqual(os.listdir(r[0]), [])
    self.assertEqual(os.listdir(r[1]), [])

  @classmethod
  def tearDownClass(cls):
    os.remove('input.txt')
    for file in glob.glob('*.test'):
      os.remove(file)
    shutil.rmtree('analysis_root', ignore_errors=True)
    shutil.rmtree('output_root', ignore_errors=True)
