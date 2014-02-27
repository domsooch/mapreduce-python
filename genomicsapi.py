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
import os

from google.appengine.api import memcache
from google.appengine.api.urlfetch_errors import DeadlineExceededError

from oauth2client.appengine import AppAssertionCredentials

from oauth2client import appengine

client_secrets = os.path.join(os.path.dirname(__file__), 'client_secrets.json')

decorator = appengine.oauth2decorator_from_clientsecrets(
  client_secrets,
  scope=[
    'https://www.googleapis.com/auth/genomics',
    'https://www.googleapis.com/auth/devstorage.read_write'
  ])


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
      # May want to specfify just the fields that we need.
      #'includeFields': ["position", "alignedBases"]
      }

    logging.debug("Request Body:")
    logging.debug(body)

    content = self._get_content("reads/search", body=body)
    return content

  def _get_content(self, path, method='POST', body=None):
    credentials = AppAssertionCredentials(scope=[
    'https://www.googleapis.com/auth/genomics',
    'https://www.googleapis.com/auth/devstorage.read_write'
    ])
    http = credentials.authorize(httplib2.Http(memcache))
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
