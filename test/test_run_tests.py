import run_tests as rt
import unittest

class Test(unittest.TestCase):
  def test_validate_urls(self):
    self.assertTrue(rt._is_http_url_entry('http://tests.com/mytest'))
    self.assertFalse(rt._is_http_url_entry('https://tests.com/mytest'))
    self.assertFalse(rt._is_http_url_entry('https://tests.com/dir/'))
    self.assertFalse(rt._is_http_url_entry('http://tests.com'))
    self.assertFalse(rt._is_http_url_entry('http://tests.com//mytest'))
    self.assertFalse(rt._is_http_url_entry('http://tests.com/ /mytest'))

  def test_validate_paths(self):
    self.assertTrue(rt._is_path_entry('abc/xyz'))
    self.assertTrue(rt._is_path_entry('/abc/xyz'))
    self.assertFalse(rt._is_path_entry('abc/xyz/'))
    self.assertFalse(rt._is_path_entry('~abc'))
    self.assertFalse(rt._is_path_entry('^abc'))
    self.assertTrue(rt._is_path_entry('~/abc'))
    self.assertTrue(rt._is_path_entry('^/abc'))

  def test_validate_entries(self):
    self.assertTrue(rt._is_valid_entry(''))
    self.assertTrue(rt._is_valid_entry('# comment'))
    self.assertTrue(rt._is_valid_entry('archive{rt._archive_suf'))
