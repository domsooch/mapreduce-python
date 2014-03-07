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
import os

from common import Common
from genomicsapi import GenomicsAPI
from mapreduce import base_handler
from mapreduce import mapreduce_pipeline

Common.initialize()

def generate_coverage_map(data):
  """Generate coverage map function."""
  (content, sequenceStart, sequenceEnd) = data
  reads = content['reads'] if 'reads' in content else []
  coverage = GenomicsAPI.compute_coverage(reads, sequenceStart,
                                          sequenceEnd)
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
      "pipeline.generate_coverage_map",
      "pipeline.generate_coverage_reduce",
      "input_reader.GenomicsAPIInputReader",
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
      "pipeline.consolidate_output_map",
      "pipeline.consolidate_output_reduce",
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


