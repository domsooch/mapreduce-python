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
import httplib2
import jinja2
import json
import logging
import os
import pickle
import re
import webapp2

from google.appengine.ext import db

from google.appengine.api import files
from google.appengine.api import taskqueue
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.api.urlfetch_errors import DeadlineExceededError
from google.appengine.api import memcache

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
from mockgenomicsapi import MockGenomicsAPI

from oauth2client import appengine

# In the local development environment, implement some customizations.
if os.environ['SERVER_SOFTWARE'].startswith('Development'):
  # Add color to logging messages.
  logging.addLevelName(logging.ERROR,
                       "\033[1;31m%s\033[1;m\t" %
                       logging.getLevelName(logging.ERROR))
  logging.addLevelName(logging.WARNING,
                       "\033[1;33m%s\033[1;m\t" %
                       logging.getLevelName(logging.WARNING))
  logging.addLevelName(logging.INFO,
                       "\033[1;32m%s\033[1;m\t" %
                       logging.getLevelName(logging.INFO))
  logging.addLevelName(logging.DEBUG,
                       "\033[1;36m%s\033[1;m\t" %
                       logging.getLevelName(logging.DEBUG))

# Increase timeout to the maximum for all requests
urlfetch.set_default_fetch_deadline(60)

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
    'useMockData': True,
    'runPipeline': True,
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
        pipeline = CoveragePipeline(readsetId, sequenceName, sequenceStart,
                                    sequenceEnd, useMockData)
        pipeline.start()
        self.redirect(pipeline.base_path + "/status?root="
                      + pipeline.pipeline_id)
        return

      if useMockData:
        # Use the mock to get coverage information.
        mock = MockGenomicsAPI()
        content = mock.read_search(readsetId, sequenceName, sequenceStart,
                                   sequenceEnd)
      else:
        # Make the API call here to process directly.
        try:
          api = GenomicsAPIClientOAuth()
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


class CoveragePipeline(base_handler.PipelineBase):
  """A pipeline to run Word count demo.

  Args:
    blobkey: blobkey to process as string. Should be a zip archive with
      text files inside.
  """

  def run(self, readsetId, sequenceName, sequenceStart, sequenceEnd,
          useMockData):
    logging.debug("Running Pipeline for readsetId %s" % readsetId)
    output = yield mapreduce_pipeline.MapreducePipeline(
      "generate_coverage",
      "main.generate_coverage_map",
      "main.generate_coverage_reduce",
      "main.GenomicsAPIInputReader",
      "mapreduce.output_writers.BlobstoreOutputWriter",
      mapper_params={
        "input_reader": {
          "readsetId": readsetId,
          "sequenceName": sequenceName,
          "sequenceStart": sequenceStart,
          "sequenceEnd": sequenceEnd,
          "useMockData": useMockData,
        },
        "output_writer": {
        },
      },
      reducer_params={
        "mime_type": "text/plain",
      },
      shards=16)
    yield ProcessPipelineOutput(output)


class ProcessPipelineOutput(base_handler.PipelineBase):
  """A pipeline to proecss the result of the MapReduce job.

  Args:
    output: the blobstore location where the output of the job is stored
  """

  def run(self, output):
    blobstorePath = output[0]
    # TODO determine if you are running locally or not and change the url
    # accordingly.
    url = str.replace(str(blobstorePath), "/blobstore/",
                      "http://localhost:8000/blobstore/blob/")
    logging.info("Pipeline Map Reduce has been completed. "
                 "Results can be found here: %s" % url)


app = webapp2.WSGIApplication(
  [
    ('/', MainHandler),
    (decorator.callback_path, decorator.callback_handler()),
  ],
  debug=True)

#
# Move to different file???
#

class GenomicsAPIInputReader(input_readers.InputReader):
  """Input reader for Genomics API
  """

  # Supported parameters
  READSET_ID_PARAM = "readsetId"
  SEQUENCE_NAME_PARAM = "sequenceName"
  SEQUEQNCE_START_PARAM = "sequenceStart"
  SEQUEQNCE_END_PARAM = "sequenceEnd"
  USE_MOCK_DATA_PARAM = "useMockData"

  # Maximum number of shards to allow.
  _MAX_SHARD_COUNT = 256

  # Other internal configuration constants
  _JSON_PICKLE = "pickle"

  # Input reader can also take in start and end filenames and do
  # listbucket. This saves space but has two cons.
  # 1. Files to read are less well defined: files can be added or removed over
  #    the lifetime of the MR job.
  # 2. A shard has to process files from a contiguous namespace.
  #    May introduce staggering shard.
  def __init__(self, readsetId=None, sequenceName=None, sequenceStart=None,
               sequenceEnd=None, useMockData=True):
    """Initialize a GenomicsAPIInputReader instance.

    Args:
      TBD
    """
    logging.debug("GenomicsAPIInputReader __init__() is called.")
    self._readsetId = readsetId
    self._sequenceName = sequenceName
    self._sequenceStart = sequenceStart
    self._sequenceEnd = sequenceEnd
    self._useMockData = useMockData
    self._firstTime = True
    self._nextPageToken = None

  @classmethod
  def validate(cls, mapper_spec):
    """Validate mapper specification.

    Args:
      mapper_spec: an instance of model.MapperSpec

    Raises:
      BadReaderParamsError if the specification is invalid for any reason such
        as missing the bucket name or providing an invalid bucket name.
    """
    reader_spec = input_readers._get_params(mapper_spec, allow_old=False)

    logging.debug("GenomicsAPIInputReader validate() is called.")

    # Readset id is required.
    if cls.READSET_ID_PARAM not in reader_spec:
      raise errors.BadReaderParamsError("%s is required for the Genomics API" %
                                        cls.READSET_ID_PARAM)

  @classmethod
  def split_input(cls, mapper_spec):
    """Returns a list of input readers.

    An equal number of input files are assigned to each shard (+/- 1). If there
    are fewer files than shards, fewer than the requested number of shards will
    be used. Input files are currently never split (although for some formats
    could be and may be split in a future implementation).

    Args:
      mapper_spec: an instance of model.MapperSpec.

    Returns:
      A list of InputReaders. None when no input data can be found.
    """
    reader_spec = input_readers._get_params(mapper_spec, allow_old=False)
    readsetId = reader_spec[cls.READSET_ID_PARAM]
    sequenceName = reader_spec[cls.SEQUENCE_NAME_PARAM]
    sequenceStart = reader_spec.get(cls.SEQUEQNCE_START_PARAM)
    sequenceEnd = reader_spec.get(cls.SEQUEQNCE_END_PARAM)
    useMockData = reader_spec.get(cls.USE_MOCK_DATA_PARAM)

    # TODO if you are doing all sequences then you need to take sequence name
    # into account as well.
    # For now assume we are only doing a single sequence name.

    # Divide the range by the shard count to get the step.
    shard_count = min(cls._MAX_SHARD_COUNT, mapper_spec.shard_count)
    range_length = ((sequenceEnd + 1) - sequenceStart) // shard_count
    if range_length == 0:
      range_length = 1
    logging.debug("GenomicsAPIInputReader split_input() "
                  "shards: %d range_length: %d" %
                  (mapper_spec.shard_count, range_length))

    # Split into shards
    readers = []
    for position in xrange(shard_count - 1):
      start = sequenceStart + (range_length * position)
      end = start + range_length - 1
      logging.debug("GenomicsAPIInputReader split_input() start: %d end: %d." %
                    (start, end))
      readers.append(cls(readsetId, sequenceName, start, end, useMockData))
    start = sequenceStart + (range_length * (shard_count - 1))
    end = sequenceEnd
    logging.debug("GenomicsAPIInputReader split_input() start: %d end: %d." %
                    (start, end))
    readers.append(cls(readsetId, sequenceName, start, end, useMockData))

    return readers

  @classmethod
  def from_json(cls, state):
    obj = pickle.loads(state[cls._JSON_PICKLE])
    return obj

  def to_json(self):
    return {self._JSON_PICKLE: pickle.dumps(self)}

  def next(self):
    """Returns the data from the call to the GenomicsAPI
    Raises:
      StopIteration: The list of files has been exhausted.
    """

    # If it's your first time or you have a tokent then make the call.
    if self._firstTime or self._nextPageToken:
      # Determine if we are using the real or mock Genomics API.
      api = MockGenomicsAPI() if self._useMockData else GenomicsAPI()
      # Get the results
      try:
        content = api.read_search(self._readsetId, self._sequenceName,
                                   self._sequenceStart, self._sequenceEnd,
                                   self._nextPageToken)
        self._firstTime = False
      except ApiException as exception:
        errorMessage = exception.message
        # TODO not sure what we do here if we can't get content?
        raise StopIteration()

      if content is not None:
        if 'nextPageToken' in content:
          self._nextPageToken = content["nextPageToken"]
        if 'reads' in content:
          return (content, self._sequenceStart, self._sequenceEnd)
      else:
        # TODO not sure what we do here if we got content but not as expected?
        raise StopIteration()
    else:
      # All Done
      logging.debug("GenomicsAPIInputReader next() is Done "
                    "start: %d end: %d." %
                    (self._sequenceStart, self._sequenceEnd))
      raise StopIteration()


class GenomicsAPIClientOAuth():
  """ Provides and interface for which to make Google Genomics API calls.
  """

  def read_search(self, readsetId, sequenceName, sequenceStart, sequenceEnd,
                  pageToken=None):
    body = {
      'readsetIds': [readsetId],
      'sequenceName': sequenceName,
      'sequenceStart': sequenceStart,
      'sequenceEnd': sequenceEnd,
      'pageToken': pageToken
      # May want to specfify just the fields that we need.
      #'includeFields': ["position", "alignedBases"]
      }

    logging.debug("Request Body:")
    logging.debug(body)

    content = self._get_content("reads/search", body=body)
    return content

  def _get_content(self, path, method='POST', body=None):
    http = decorator.http()
    try:
      response, content = http.request(
        uri="https://www.googleapis.com/genomics/v1beta/%s" % path,
        method=method, body=json.dumps(body) if body else None,
        headers={'Content-Type': 'application/json; charset=UTF-8'})
    except DeadlineExceededError:
      raise ApiException('API fetch timed out')

    # Log results to debug
    logging.debug("Response:")
    logging.debug(response)
    logging.debug("Content:")
    logging.debug(content)

    # Parse the content as json.
    content = json.loads(content)

    if response.status == 404:
      raise ApiException('API not found')
    elif response.status == 400:
      raise ApiException('API request malformed')
    elif response.status != 200:
      if 'error' in content:
        logging.error("Error Code: %s Message: %s" %
                      (content['error']['code'], content['error']['message']))
      raise ApiException("Something went wrong with the API call. "
                         "Please check the logs for more details.")
    return content
