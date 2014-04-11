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

import datetime
import jinja2
import os
import webapp2

from google.appengine.api import users

from common import Common
from genomicsapi import GenomicsAPI
from pipeline import PipelineGenerateCoverage

Common.initialize()

JINJA_ENVIRONMENT = jinja2.Environment(
  loader=jinja2.FileSystemLoader('templates'),
  autoescape=True,
  extensions=['jinja2.ext.autoescape'])


class MainHandler(webapp2.RequestHandler):
  """The main page that users will interact with, which presents users with
  the ability to upload new data or run MapReduce jobs on their existing data.
  """

  # Provide default settings for the user that they can then override.
  DEFAULT_SETTINGS = {
    'readsetId': 'CJ_ppJ-WCxDxrtDr5fGIhBA=',
    'sequenceName': 'chr20',
    'sequenceStart': 68101,
    'sequenceEnd': 68164,
  }

  def get(self):
    username = users.User().nickname()
    template = JINJA_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render({
      'username': username,
      'version': self._get_version(),
      'targets': GenomicsAPI.TARGETS,
      'settings': MainHandler.DEFAULT_SETTINGS,
    }))

  def post(self):
    # Collect inputs.
    readsetId = self.request.get('readsetId')
    sequenceName = self.request.get('sequenceName')
    sequenceStart = int(self.request.get('sequenceStart'))
    sequenceEnd = int(self.request.get('sequenceEnd'))

    # Start a mapreduce pipeline to generate coverage
    # Then redirect to the status page
    pipeline = PipelineGenerateCoverage(readsetId, sequenceName,
                                        sequenceStart, sequenceEnd)
    pipeline.start()
    self.redirect('%s/status?root=%s' %
                  (pipeline.base_path, pipeline.pipeline_id))

  def _get_version(self):
    version = self.request.environ['CURRENT_VERSION_ID'].split('.')
    name = version[0]
    date = datetime.datetime.fromtimestamp(long(version[1]) >> 28)
    if os.environ['SERVER_SOFTWARE'].startswith('Development'):
      date = datetime.datetime.now()
    return name + ' as of ' + date.strftime('%Y-%m-%d %X')

app = webapp2.WSGIApplication(
  [
    ('/', MainHandler),
  ],
  debug=True)

