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

Example Genomics Map Reduce Input Reader
"""

import logging
import pickle

from common import Common

from mapreduce import errors
from mapreduce import input_readers

from genomicsapi import GenomicsAPI
from genomicsapi import ApiException

Common.initialize()

class GenomicsAPIInputReader(input_readers.InputReader):
  """Input reader for Genomics API
  """

  # Supported parameters
  READSET_ID_PARAM = "readsetId"
  SEQUENCE_NAME_PARAM = "sequenceName"
  SEQUEQNCE_START_PARAM = "sequenceStart"
  SEQUEQNCE_END_PARAM = "sequenceEnd"

  # Maximum number of shards to allow.
  _MAX_SHARD_COUNT = 256

  # Other internal configuration constants
  _JSON_PICKLE = "pickle"

  def __init__(self, readsetId=None, sequenceName=None, sequenceStart=None,
               sequenceEnd=None):
    self._readsetId = readsetId
    self._sequenceName = sequenceName
    self._sequenceStart = sequenceStart
    self._sequenceEnd = sequenceEnd
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

    # TODO if you are doing all sequences then you need to take sequence name
    # into account as well.
    # For now assume we are only doing a single sequence name.

    # Divide the range by the shard count to get the step.
    shard_count = min(cls._MAX_SHARD_COUNT, mapper_spec.shard_count)
    range_length = ((sequenceEnd + 1) - sequenceStart) // shard_count
    if range_length == 0:
      range_length = 1

    # Split into shards
    readers = []
    for position in xrange(shard_count - 1):
      start = sequenceStart + (range_length * position)
      end = start + range_length - 1
      logging.debug("GenomicsAPIInputReader split_input() start: %d end: %d.",
                   start, end)
      readers.append(cls(readsetId, sequenceName, start, end))
    start = sequenceStart + (range_length * (shard_count - 1))
    end = sequenceEnd

    logging.debug("GenomicsAPIInputReader split_input() start: %d end: %d.",
                 start, end)
    readers.append(cls(readsetId, sequenceName, start, end))

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
      StopIteration: The data has been exhausted.
    """

    # If it's your first time or you have a token then make the call.
    if self._firstTime or self._nextPageToken:
      api = GenomicsAPI()

      # Get the results
      try:
        content = api.read_search(self._readsetId, self._sequenceName,
                                   self._sequenceStart, self._sequenceEnd,
                                   self._nextPageToken)
        self._firstTime = False
      except ApiException as exception:
        logging.warning("API exception: %s" % exception.message)
        raise StopIteration()

      self._nextPageToken = content["nextPageToken"] if 'nextPageToken' in content else None
      return content, self._sequenceStart, self._sequenceEnd
    else:
      raise StopIteration()
