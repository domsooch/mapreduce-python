"""
Copyright 2014 Google Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Example Genomics Map Reduce
"""

import logging
import os

class once(object):
  __slots__ = ("func", "result", "methods")
  def __init__(self, func):
    self.func = func
  def __call__(self, *args, **kw):
    try:
      return self.result
    except AttributeError:
      self.result = self.func(*args, **kw)
      return self.result
  def __get__(self, instance, cls):
    method = self.func.__get__(instance, cls)
    try:
      return self.methods[method]
    except (AttributeError,KeyError):
      decorated = once(method)
      try:
        self.methods[method] = decorated
      except AttributeError:
        self.methods = { method : decorated }
      return decorated
  def __eq__(self, other):
    return isinstance(other, once) and other.func == self.func
  def __hash__(self):
    return hash(self.func)

class Common():

 @once
 @staticmethod
 def initialize():
    # In the local development environment, implement some customizations.
    if os.environ['SERVER_SOFTWARE'].startswith('Development'):
      # Add color to logging messages.
      logging.addLevelName(logging.ERROR,
                           "\033[0;31m%s\033[0m\t" %
                           logging.getLevelName(logging.ERROR))
      logging.addLevelName(logging.WARNING,
                           "\033[0;33m%s\033[0m\t" %
                           logging.getLevelName(logging.WARNING))
      logging.addLevelName(logging.INFO,
                           "\033[0;32m%s\033[0m\t" %
                           logging.getLevelName(logging.INFO))
      logging.addLevelName(logging.DEBUG,
                           "\033[0;36m%s\033[0m\t" %
                           logging.getLevelName(logging.DEBUG))
