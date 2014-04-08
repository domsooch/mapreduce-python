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

import httplib2
import json
import logging
import socket
import os

from common import Common

from collections import defaultdict

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api.urlfetch_errors import DeadlineExceededError

from oauth2client.appengine import AppAssertionCredentials

Common.initialize()

# Increase timeout to the maximum for all requests and use caching
urlfetch.set_default_fetch_deadline(60)
socket.setdefaulttimeout(60)

class ApiException(Exception):
  pass

class GenomicsAPI():
  """ Provides and interface for which to make Google Genomics API calls.
  """
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

  def read_search(self, readsetId, sequenceName, sequenceStart, sequenceEnd,
                  pageToken=None):
    logging.info("GenomicsAPI read_search() start: %d end: %d token: %s",
                  sequenceStart, sequenceEnd, str(pageToken))

    # Create the body with the parameters.
    body = {
      'readsetIds': [readsetId],
      'sequenceName': sequenceName,
      'sequenceStart': sequenceStart,
      'sequenceEnd': sequenceEnd,
      'pageToken': pageToken
      # May want to specify just the fields that we need.
      #'includeFields': ["position", "alignedBases"]
    }

    return self._get_content("reads/search", body=body)

  def _get_content(self, path, method='POST', body=None):
    scope = [
      'https://www.googleapis.com/auth/genomics'
    ]
    # The API Key is required when deployed to app engine
    api_key = os.environ['API_KEY']
    credentials = AppAssertionCredentials(scope=scope)
    http = httplib2.Http(cache=memcache)
    http = credentials.authorize(http)

    try:
      response, content = http.request(
        uri="https://www.googleapis.com/genomics/v1beta/%s?key=%s"
            % (path, api_key),
        method=method, body=json.dumps(body) if body else None,
        headers={'Content-Type': 'application/json; charset=UTF-8'})
    except DeadlineExceededError:
      raise ApiException('API fetch timed out')

    try:
      content = json.loads(content)
    except ValueError:
      logging.error("non-json api content %s" % content)
      raise ApiException('The API returned invalid JSON')

    if response.status >= 300:
      logging.error("error api response %s" % response)
      logging.error("error api content %s" % content)
      if 'error' in content:
        raise ApiException(content['error']['message'])
      else:
        raise ApiException('Something went wrong with the API call!')
    return content


  @staticmethod
  def compute_coverage(reads, sequenceStart, sequenceEnd):
    """Takes the json results from the Genomics API call and computes
    coverage. """
    #logging.info("Computing coverage from start: %d to end: %d.",
    #             sequenceStart, sequenceEnd)
    coverage = defaultdict(int)
    if len(reads) > 0:
      for read in reads:
        # Check the read against every sequence.
        read_end = read["position"] + len(read["alignedBases"])
        for sequence in range(read["position"], read_end):
          if (sequenceStart <= sequence) and (sequence <= sequenceEnd):
            coverage[sequence] += 1

    # If you didn't get a value then set it to 0.
    for sequence in range(sequenceStart, sequenceEnd + 1):
      if sequence not in coverage:
        coverage[sequence] = 0

    logging.info("Processed %d reads from start: %d to end: %d.",
                 len(reads), sequenceStart, sequenceEnd)
    return coverage
