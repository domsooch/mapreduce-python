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

from common import Common

Common.initialize()

class MockGenomicsAPI():
  """ Provides a mock for the Genomics API so that you can call use this class
  instead of actual Genomics API calls for testing purposes.
  """

  def read_search(self, readsetId, sequenceName, sequenceStart, sequenceEnd,
                  pageToken=None):
    """ Provides mock data for the
    https://www.googleapis.com/genomics/v1beta/reads/search Genomics API call.

    The mock data will return reads such that the coverage counts should equal
    the last 2 digits of the sequence number. For example a sequenceStart 68164
    should have a coverage of 64 reads.
    """
    logging.debug("MockGenomicsAPI read_search() start: %d end: %d token: %s",
                  sequenceStart, sequenceEnd, str(pageToken))

    # If you have a pageToken then use that info to override start and end.
    if pageToken is not None:
      pair = pageToken.split(":")
      sequenceStart = int(pair[0])
      sequenceEnd = int(pair[1])

    output = {}
    # Start with the first page of 100.
    startRoundDown = sequenceStart / 100 * 100
    output["reads"] = self._create_page_of_reads(startRoundDown)
    startRoundDown += 100
    if startRoundDown < sequenceEnd:
      # Add a page token so you get called again to fetch the next page
      output["nextPageToken"] = str.format("%d:%d" % (startRoundDown, sequenceEnd))

    #logging.debug("%r", output)
    return output

  def _create_page_of_reads(self, startPosition):
    """ Creates a page of data staring from page XXX00 and ending at page
    XXX99. Page XXX00 has 0 coverage, page XXX01 has a coverage of
    1 read, ... page XXX99 has a coverage of 99 reads.
    """
    reads = []
    endPosition = startPosition + 100
    for position in range(startPosition + 1, endPosition):
      reads.append(self._create_read(position, endPosition - position))
    return reads

  def _create_read(self, position, length):
    read = {
      "position": position,
      "alignedBases": "X" * length,
    }
    return read
