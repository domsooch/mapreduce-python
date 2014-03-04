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
import logging
import os
import pickle
import webapp2

from google.appengine.ext import db

from google.appengine.api import files
from google.appengine.api import taskqueue
from google.appengine.api import users

from oauth2client.appengine import AppAssertionCredentials

from collections import defaultdict

from mapreduce import base_handler
from mapreduce import context
from mapreduce import errors
from mapreduce import input_readers
from mapreduce import mapreduce_pipeline
from mapreduce import operation
from mapreduce import shuffler

from genomicsapi import GenomicsAPI
from genomicsapi import ApiException
from input_reader import GenomicsAPIInputReader
from mock_genomicsapi import MockGenomicsAPI

from oauth2client import appengine

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

JINJA_ENVIRONMENT = jinja2.Environment(
  loader=jinja2.FileSystemLoader('templates'),
  autoescape=True,
  extensions=['jinja2.ext.autoescape'])

client_secrets = os.path.join(os.path.dirname(__file__), 'client_secrets.json')

decorator = appengine.oauth2decorator_from_clientsecrets(
  client_secrets,
  scope=[
    'https://www.googleapis.com/auth/genomics',
    'https://www.googleapis.com/auth/devstorage.read_write'
  ])


class GenomicsCoverageStatistics(db.Model):
  """Holds the calculated genomics coverage statistics.
  """

  __SEP = ".."
  __NEXT = "./"

  readsetId = db.StringProperty()
  sequenceName = db.StringProperty()
  sequence = db.IntegerProperty()
  coverage = db.IntegerProperty()
  date = db.DateTimeProperty()

  @staticmethod
  def getFirstKeyForReadsetId(readsetId):
    """Helper function that returns the first possible key a user could own.

    This is useful for table scanning, in conjunction with
    getLastKeyForReadsetId.

    Args:
      readsetId: The given ureadsetId.
    Returns:
      The internal key representing the earliest possible key that a user could
      own (although the value of this key is not able to be used for actual
      user data).
    """

    return db.Key.from_path("GenomicsCoverageStatistics",
                            readsetId + GenomicsCoverageStatistics.__SEP)

  @staticmethod
  def getLastKeyForReadsetId(readsetId):
    """Helper function that returns the last possible key a user could own.

    This is useful for table scanning, in conjunction with getFirstKeyForUser.

    Args:
      username: The given user's e-mail address.
    Returns:
      The internal key representing the last possible key that a user could
      own (although the value of this key is not able to be used for actual
      user data).
    """

    return db.Key.from_path("GenomicsCoverageStatistics",
                            readsetId + GenomicsCoverageStatistics.__NEXT)

  @staticmethod
  def getKeyName(readsetId, sequenceName, sequence):
    """Returns the internal key for a particular item in the database.

    Our items are stored with keys of the form 'user/date/blob_key' ('/' is
    not the real separator, but __SEP is).

    Args:
      username: The given user's e-mail address.
      date: A datetime object representing the date and time that an input
        file was uploaded to this app.
      blob_key: The blob key corresponding to the location of the input file
        in the Blobstore.
    Returns:
      The internal key for the item specified by (username, date, blob_key).
    """

    sep = GenomicsCoverageStatistics.__SEP
    return str(readsetId + sep + sequenceName + sep + str(sequence))

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
  # taken from the python-client app. Maybe refactor to common place ???
  TARGETS = [
    {'name': "chr1", 'sequenceLength': 249250621},
    {'name': "chr2", 'sequenceLength': 243199373},
    {'name': "chr3", 'sequenceLength': 198022430},
    {'name': "chr4", 'sequenceLength': 191154276},
    {'name': "chr5", 'sequenceLength': 180915260},
    {'name': "chr6", 'sequenceLength': 171115067},
    {'name': "chr7", 'sequenceLength': 159138663},
    {'name': "chr8", 'sequenceLength': 146364022},
    {'name': "chr9", 'sequenceLength': 141213431},
    {'name': "chr10", 'sequenceLength': 135534747},
    {'name': "chr11", 'sequenceLength': 135006516},
    {'name': "chr12", 'sequenceLength': 133851895},
    {'name': "chr13", 'sequenceLength': 115169878},
    {'name': "chr14", 'sequenceLength': 107349540},
    {'name': "chr15", 'sequenceLength': 102531392},
    {'name': "chr16", 'sequenceLength': 90354753},
    {'name': "chr17", 'sequenceLength': 81195210},
    {'name': "chr18", 'sequenceLength': 78077248},
    {'name': "chr19", 'sequenceLength': 59128983},
    {'name': "chr20", 'sequenceLength': 63025520},
    {'name': "chr21", 'sequenceLength': 48129895},
    {'name': "chr22", 'sequenceLength': 51304566},
    {'name': "chrX", 'sequenceLength': 155270560},
    {'name': "chrY", 'sequenceLength': 59373566},
  ]

  # Provide default settings for the user that they can then override.
  DEFAULT_SETTINGS = {
    'readsetId': "CJ_ppJ-WCxD-2oXg667IhDM=",
    'sequenceName': "chr20",
    'sequenceStart': 68101,
    'sequenceEnd': 68164,
    'useMockData': False,
    'runPipeline': False,
  }

  @decorator.oauth_aware
  def get(self):
    if decorator.has_credentials():
      username = users.User().nickname()

      template = JINJA_ENVIRONMENT.get_template('index.html')
      self.response.out.write(template.render({
        "username": username,
        "targets": MainHandler.TARGETS,
        "settings": MainHandler.DEFAULT_SETTINGS,
      }))

    else:
      template = JINJA_ENVIRONMENT.get_template('grantaccess.html')
      self.response.write(template.render({
        'url': decorator.authorize_url()
      }))

  @decorator.oauth_aware
  def post(self):
    # Collect inputs.
    readsetId = self.request.get("readsetId")
    sequenceName = self.request.get('sequenceName')
    sequenceStart = int(self.request.get('sequenceStart'))
    sequenceEnd = int(self.request.get('sequenceEnd'))
    useMockData = self.request.get('useMockData')

    # TODO: Validate inputs such as sequence start and end to make
    # sure they are in bounds based on TARGETS.

    content = None
    coverage = None
    errorMessage = None

    if self.request.get("submitRead"):
      # Use the API to get the requested data.
      # If you are running the real pipeline map reduce then hit it.
      if self.request.get('runPipeline'):
        logging.debug("Running pipeline")
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
        content = api.read_search(readsetId, sequenceName, sequenceStart,
                                   sequenceEnd)
      except ApiException as exception:
        errorMessage = exception.message

    elif self.request.get("submitReadSample"):
      # Read in local sample data which is based off of default settings.
      body = MainHandler.DEFAULT_SETTINGS
      path = os.path.join(os.path.split(__file__)[0],
                          'static/listRead_SampleData.json')
      file = open(path, 'r')
      content = file.read()
      file.close()
      content = json.loads(content)

    # If you have content then compute and store the results.
    if content is not None:
      if 'reads' in content:
        # Calculate results
        coverage = compute_coverage(content, sequenceStart, sequenceEnd)
        # TODO make a setting to turn this on/off?
        #store_coverage(readsetId, sequenceName, coverage)
      else:
        errorMessage = "There API did not return any reads to process."
    else:
      errorMessage = "No content was returned to process."

    # Render template with results or error.
    username = users.User().nickname()
    template = JINJA_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render({
      "username": username,
      "targets": MainHandler.TARGETS,
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


def compute_coverage(content, sequenceStart, sequenceEnd):
  """Takes the json results from the Genomics API call and computes
  coverage. """
  coverage = defaultdict(int)
  for read in content["reads"]:
    # Check the read against every sequence.
    for sequence in range(sequenceStart, sequenceEnd + 1):
      # If the position is in the range then count it as being covered
      # by that read.
      read_end = read["position"] + len(read["alignedBases"])
      if sequence >= read["position"] and sequence < read_end:
        coverage[sequence] += 1
      else:
        # Force a 0 to be recorded for that sequence number.
        coverage[sequence] += 0

  logging.debug("Processed: %d reads." % len(content["reads"]))
  return coverage


def store_coverage(readsetId, sequenceName, dict):
  for sequence, coverage in dict.iteritems():
    key = GenomicsCoverageStatistics.getKeyName(
      readsetId, sequenceName, sequence)
    s = GenomicsCoverageStatistics(key_name=key)
    s.readsetId = readsetId
    s.sequenceName = sequenceName
    s.sequence = sequence
    s.coverage = coverage
    s.date = datetime.datetime.now()
    s.put()

def generate_coverage_map(data):
  """Generate coverage map function."""
  (content, sequenceStart, sequenceEnd) = data
  coverage = compute_coverage(content, sequenceStart, sequenceEnd)
  for key, value in coverage.iteritems():
    yield (key, value)

def generate_coverage_reduce(key, values):
  """Generate coverage reduce function."""
  yield "%d: %d\n" % (int(key), sum(int(value) for value in values))


def consolidate_output_map(file):
  """Consolidate output map function."""
  for line in file:
    data = line.split(":")
    if len(data) == 2:
      yield (data[0], data[1])

def consolidate_output_reduce(key, values):
  """Generate coverage reduce function."""
  logging.debug("Reducing Data-> %s: %s" %
                (key,  sum(int(value) for value in values)))
  yield "%d: %d\n" % (int(key), sum(int(value) for value in values))


class PipelineGenerateCoverage(base_handler.PipelineBase):
  """A pipeline to generate coverage data

  Args:
    readsetId: the Id of the readset
  """

  def run(self, readsetId, sequenceName, sequenceStart, sequenceEnd,
          useMockData):
    logging.debug("Running Pipeline for readsetId %s" % readsetId)
    bucket = os.environ['BUCKET']

    # In the first pipeline, generate the raw coverage data.
    raw_coverage_data = yield mapreduce_pipeline.MapreducePipeline(
      "generate_coverage",
      "main.generate_coverage_map",
      "main.generate_coverage_reduce",
      "main.GenomicsAPIInputReader",
      "mapreduce.output_writers._GoogleCloudStorageOutputWriter",
      mapper_params={
        "input_reader": {
          "readsetId": readsetId,
          "sequenceName": sequenceName,
          "sequenceStart": sequenceStart,
          "sequenceEnd": sequenceEnd,
          "useMockData": useMockData,
        },
      },
      reducer_params={
        "output_writer": {
          "bucket_name": bucket,
          "content_type": "text/plain",
        },
      },
      shards=16)

    # Pass the results on to the output consolidator.
    yield PipelineConsolidateOutput(raw_coverage_data)

class PipelineConsolidateOutput(base_handler.PipelineBase):
  """A pipeline to proecss the result of the MapReduce job.

  Args:
    raw_coverage_data: the raw coverage data that is to be consolidated.
  """

  def run(self, raw_coverage_data):
    bucket = os.environ['BUCKET']
    logging.debug("Got %d raw coverage data output files to consolidate." %
                  len(raw_coverage_data))

    # Remove bucket from filenames. (Would be nice if you didn't have to do
    # this.
    paths = []
    for file in raw_coverage_data:
      paths.append(str.replace(str(file), "/" + bucket + "/", ""))

    # Create another pipeline to combine the raw coverage data into a single
    # file.
    output = yield mapreduce_pipeline.MapreducePipeline(
      "consolidate_output",
      "main.consolidate_output_map",
      "main.consolidate_output_reduce",
      "mapreduce.input_readers._GoogleCloudStorageInputReader",
      "mapreduce.output_writers._GoogleCloudStorageOutputWriter",
      mapper_params={
        "input_reader": {
           "bucket_name": bucket,
           "objects": paths,
        },
      },
      reducer_params={
        "output_writer": {
          "bucket_name": bucket,
          "content_type": "text/plain",
        },
      },
      shards=1)

    # Return back the final output results.
    yield PipelineReturnResults(output)


class PipelineReturnResults(base_handler.PipelineBase):
  """A pipeline to proecss the result of the MapReduce job.

  Args:
    output: the blobstore location where the output of the job is stored
  """

  def run(self, output):
    logging.debug('Number of output files: %d' % len(output))
    file = output[0]
    if os.environ['SERVER_SOFTWARE'].startswith('Development'):
      url = "http://localhost:8080/_ah/gcs" + file
    else:
      url = "https://storage.cloud.google.com" + file
    logging.info("Genomics pipeline completed. Results: %s" % url)


app = webapp2.WSGIApplication(
  [
    ('/', MainHandler),
    (decorator.callback_path, decorator.callback_handler()),
  ],
  debug=True)

