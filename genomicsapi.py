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
http = httplib2.Http(cache=memcache)

class ApiException(Exception):
  pass

class GenomicsAPI():
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
      # May want to specify just the fields that we need.
      #'includeFields': ["position", "alignedBases"]
      }

    logging.debug("Request Body:")
    logging.debug(body)

    content = self._get_content("reads/search", body=body)
    return content

  def _get_content(self, path, method='POST', body=None):
    scope = [
      'https://www.googleapis.com/auth/genomics',
      'https://www.googleapis.com/auth/devstorage.read_write'
    ]
    api_key = os.environ['API_KEY']
    credentials = AppAssertionCredentials(scope=scope)
    http = httplib2.Http()
    http = credentials.authorize(http)

    try:
      response, content = http.request(
        uri="https://www.googleapis.com/genomics/v1beta/%s?key=%s"
            % (path, api_key),
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


  @staticmethod
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
