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
import json
import os
import webapp2

from google.appengine.api import users

from common import Common
from database import GenomicsCoverageStatistics
from genomicsapi import GenomicsAPI
from genomicsapi import ApiException
from mock_genomicsapi import MockGenomicsAPI
from pipeline import PipelineGenerateCoverage

Common.initialize()

JINJA_ENVIRONMENT = jinja2.Environment(
  loader=jinja2.FileSystemLoader('templates'),
  autoescape=True,
  extensions=['jinja2.ext.autoescape'])


class BaseRequestHandler(webapp2.RequestHandler):
  def handle_exception(self, exception, debug_mode):
    if isinstance(exception, ApiException):
      # ApiExceptions are expected, and will return nice error messages
      # to the client
      self.response.write(exception.message)
      self.response.set_status(400)
    else:
      # All other exceptions are unexpected and should crash properly
      return webapp2.RequestHandler.handle_exception(
        self, exception, debug_mode)


class MainHandler(BaseRequestHandler):
  """The main page that users will interact with, which presents users with
  the ability to upload new data or run MapReduce jobs on their existing data.
  """

  # Provide default settings for the user that they can then override.
  DEFAULT_SETTINGS = {
    'readsetId': "CJ_ppJ-WCxDxrtDr5fGIhBA=",
    'sequenceName': "chr20",
    'sequenceStart': 68101,
    'sequenceEnd': 68164,
    'useMockData': False,
    'runPipeline': False,
  }

  def get(self):
    user = users.get_current_user()
    if user:
      username = users.User().nickname()
      template = JINJA_ENVIRONMENT.get_template('index.html')
      self.response.out.write(template.render({
        "username": username,
        "version": self._get_version(),
        "targets": GenomicsAPI.TARGETS,
        "settings": MainHandler.DEFAULT_SETTINGS,
      }))

    else:
      template = JINJA_ENVIRONMENT.get_template('grantaccess.html')
      self.response.write(template.render({
        'url': users.create_login_url('/')
      }))

  def post(self):
    # Collect inputs.
    readsetId = self.request.get("readsetId")
    sequenceName = self.request.get('sequenceName')
    sequenceStart = int(self.request.get('sequenceStart'))
    sequenceEnd = int(self.request.get('sequenceEnd'))
    useMockData = self.request.get('useMockData')

    # TODO: Validate inputs such as sequence start and end to make
    # sure they are in bounds based on TARGETS.

    reads = []
    errorMessage = None

    if self.request.get("submitRead"):
      # Use the API to get the requested data.
      # If you are running the real pipeline map reduce then hit it.
      if self.request.get('runPipeline'):
        pipeline = PipelineGenerateCoverage(readsetId, sequenceName,
                                            sequenceStart, sequenceEnd,
                                            useMockData)
        pipeline.start()
        self.redirect(pipeline.base_path + "/status?root="
                      + pipeline.pipeline_id)
        return

      # Make the API calls directly from the web ui.
      api = GenomicsAPI()
      # Use the Mock API if requested.
      if useMockData:
        api = MockGenomicsAPI()

      # Make the call.
      try:
        pageToken = None
        firstTime = True
        while firstTime or pageToken is not None:
          content = api.read_search(readsetId, sequenceName, sequenceStart,
                                    sequenceEnd, pageToken)
          firstTime = False
          if 'reads' in content:
            reads += content['reads']
          pageToken = content['nextPageToken'] if 'nextPageToken' in content\
            else None
      except ApiException as exception:
        errorMessage = exception.message

    elif self.request.get("submitReadSample"):
      # Read in local sample data which is based off of default settings.
      readsetId = MainHandler.DEFAULT_SETTINGS['readsetId']
      sequenceName = MainHandler.DEFAULT_SETTINGS['sequenceName']
      sequenceStart = MainHandler.DEFAULT_SETTINGS['sequenceStart']
      sequenceEnd = MainHandler.DEFAULT_SETTINGS['sequenceEnd']
      path = os.path.join(os.path.split(__file__)[0],
                          'static/reads-search_sample_data.json')
      file = open(path, 'r')
      content = file.read()
      file.close()
      content = json.loads(content)
      reads = content['reads']

    # If you didn't get an error compute the coverage.
    coverage = None
    if errorMessage is None:
      coverage = GenomicsAPI.compute_coverage(reads, sequenceStart, sequenceEnd)

    # TODO make a setting to turn this on/off?
    #GenomicsCoverageStatistics.store_coverage(readsetId, sequenceName,
    #                                          coverage)

    # Render template with results or error.
    username = users.User().nickname()
    template = JINJA_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render({
      "username": username,
      "version": self._get_version(),
      "targets": GenomicsAPI.TARGETS,
      "settings": {
        'readsetId': readsetId,
        'sequenceName': sequenceName,
        'sequenceStart': sequenceStart,
        'sequenceEnd': sequenceEnd,
        'useMockData': useMockData,
      },
      "errorMessage": errorMessage,
      "results": coverage,
    }))

  def _get_version(self):
    version = self.request.environ["CURRENT_VERSION_ID"].split('.')
    name = version[0]
    date = datetime.datetime.fromtimestamp(long(version[1]) >> 28)
    if os.environ['SERVER_SOFTWARE'].startswith('Development'):
      date = datetime.datetime.now()
    return name + " as of " + date.strftime("%Y-%m-%d %X")

app = webapp2.WSGIApplication(
  [
    ('/', MainHandler),
  ],
  debug=True)

