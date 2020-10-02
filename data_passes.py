class GatherDataPassException(Exception):
  pass


class FalsePass:
  def __init__(self, input_file):
    self.input_file = input_file
  def __call__(self, s):
    return False, ''


class CopyPass:
  def __init__(self, input_file, column):
    self.input_file = input_file
    self.column = column

  def __call__(self, s):
    return True, s.strip()


class ExtractPass:
  def __init__(self, input_file, column, regex, group=0, fmt=lambda s: s):
    self.input_file = input_file
    self.column = column
    self.regex = re.compile(regex)
    self.group = group
    self.fmt = fmt

  def __call__(self, s):
    m = self.regex.search(s)
    if m:
      return True, self.fmt(m.group(self.group))

    return True, self.fmt('')


class CheckPass:
  def __init__(self, input_file, regex=None, check=lambda s: True):
    self.input_file = input_file
    if regex:
      self.regex = re.compile(regex)
    else:
      self.regex = None
    self.check = check

  def __call__(self, s):
    if self.regex:
      m = self.regex.search(s)
      if not m:
        return False, ''

    return self.check(s), ''


class ProcessPass:
  def __init__(self, input_file, column, f=lambda s: s):
    self.input_file = input_file
    self.column = column
    self.f = f

  def __call__(self, s):
    return True, self.f(s)
