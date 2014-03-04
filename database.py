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

from common import Common

from google.appengine.ext import db


Common.initialize()

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

  @staticmethod
  def store_coverage(readsetId, sequenceName, dict):
    for sequence, coverage in dict.iteritems():
      key = GenomicsCoverageStatistics.getKeyName(readsetId, sequenceName,
                                                  sequence)
      s = GenomicsCoverageStatistics(key_name=key)
      s.readsetId = readsetId
      s.sequenceName = sequenceName
      s.sequence = sequence
      s.coverage = coverage
      s.date = datetime.datetime.now()
      s.put()