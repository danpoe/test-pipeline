
class FalsePass:
  def __init__(self, input_file):
    self.input_file = input_file
  def __call__(self, s):
    return False, ''
