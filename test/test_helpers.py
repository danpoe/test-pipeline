import pathlib
import test_pipeline
import unittest
import tempfile

class Test(unittest.TestCase):
  def test_validate_urls(self):
    tp = test_pipeline.TestPipeline()
    self.assertTrue(tp._is_http_url_entry('http://tests.com/mytest'))
    self.assertFalse(tp._is_http_url_entry('https://tests.com/mytest'))
    self.assertFalse(tp._is_http_url_entry('https://tests.com/dir/'))
    self.assertFalse(tp._is_http_url_entry('http://tests.com'))
    self.assertFalse(tp._is_http_url_entry('http://tests.com//mytest'))
    self.assertFalse(tp._is_http_url_entry('http://tests.com/ /mytest'))

  def test_validate_paths(self):
    tp = test_pipeline.TestPipeline()
    self.assertTrue(tp._is_path_entry('abc/xyz'))
    self.assertTrue(tp._is_path_entry('/abc/xyz'))
    self.assertFalse(tp._is_path_entry('abc/xyz/'))
    self.assertFalse(tp._is_path_entry('~abc'))
    self.assertFalse(tp._is_path_entry('^abc'))
    self.assertTrue(tp._is_path_entry('~/abc'))
    self.assertTrue(tp._is_path_entry('^/abc'))

  def test_validate_entries(self):
    tp = test_pipeline.TestPipeline()
    self.assertTrue(tp._is_valid_entry(''))
    self.assertTrue(tp._is_valid_entry('# comment'))

  def test_copy_and_merge(self):
    tp = test_pipeline.TestPipeline()
    with tempfile.TemporaryDirectory() as d:
      # we use suffixes to indicate whether files and folders are unique (`u`)
      # or common (`c`) between the two top-level folders that are merged
      d = pathlib.Path(d)
      # source folder
      d1 = d / 'dir1u'
      d1.mkdir()
      (d1 / 'file1u').touch()
      (d1 / 'file2c').touch()
      (d1 / 'dir2u').mkdir()
      (d1 / 'dir2u' / 'file3u').touch()
      (d1 / 'dir3c').mkdir()
      (d1 / 'dir3c' / 'file3u').touch()
      (d1 / 'dir3c' / 'file4c').touch()
      # target folder
      d2 = d / 'dir2u'
      d2.mkdir()
      (d2 / 'file2c').touch()
      (d2 / 'dir3c').mkdir()
      (d2 / 'dir3c' / 'file4c').touch()
      (d2 / 'dir3c' / 'file5u').touch()
      # now copy and merge
      tp._copy_and_merge(d1, d2)
      # check result
      self.assertTrue(d2.is_dir())
      self.assertTrue((d2 / 'file1u').is_file())
      self.assertTrue((d2 / 'file2c').is_file())
      self.assertTrue((d2 / 'dir2u').is_dir())
      self.assertTrue((d2 / 'dir2u' / 'file3u').is_file())
      self.assertTrue((d2 / 'dir3c').is_dir())
      self.assertTrue((d2 / 'dir3c' / 'file3u').is_file())
      self.assertTrue((d2 / 'dir3c' / 'file4c').is_file())
      self.assertTrue((d2 / 'dir3c' / 'file5u').is_file())
