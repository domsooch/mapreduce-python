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

import cloudstorage as gcs
import logging
import os

from common import Common
from genomicsapi import GenomicsAPI
from google.appengine.api import app_identity
from mapreduce import base_handler
from mapreduce import mapreduce_pipeline

Common.initialize()

def get_bucket_name():
  return os.getenv('BUCKET', app_identity.get_default_gcs_bucket_name())

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
      # So that we get the data properly sorted numerically in the end.
      key = str.format("%09d" % int(data[0]))
      yield (key, data[1])

def consolidate_output_reduce(key, values):
  """Consolidate output reduce function."""
  yield "%d: %d\n" % (int(key), sum(int(value) for value in values))


class PipelineGenerateCoverage(base_handler.PipelineBase):
  """A pipeline to generate coverage data

  Args:
    readsetId: the Id of the readset
  """

  def run(self, readsetId, sequenceName, sequenceStart, sequenceEnd):
    #logging.debug("Running Pipeline for readsetId: %s", readsetId)
    bucket = get_bucket_name()
    shards = os.environ['MAPREDUCE_SHARDS']

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
        },
      },
      reducer_params={
        "output_writer": {
          "bucket_name": bucket,
          "content_type": "text/plain",
        },
      },
      shards=shards)

    # Since running the MR to consolidate the output take a very long time,
    # for now just return the individual results.
    yield PipelineReturnIndividualResults(readsetId, sequenceName,
                                          sequenceStart, sequenceEnd,
                                          raw_coverage_data)

class PipelineReturnIndividualResults(base_handler.PipelineBase):
  """A pipeline to process the result of the MapReduce job.

  Args:
    output: the blobstore location where the output of the job is stored
  """

  def run(self, readsetId, sequenceName, sequenceStart, sequenceEnd, files):
    #logging.debug('Number of output files: %d', len(output))

    # If you have a setting to copy it over, do so
    local = os.environ['SERVER_SOFTWARE'].startswith('Development')
    bucket = get_bucket_name()
    dir = os.getenv('OUTPUT_DIRECTORY', 'genomics_mr_results')
    path = str.format("/%s/%s/%s/%s" %
                      (bucket, dir, str(readsetId), str(sequenceName)))
    shard = 0
    for file in files:
      dst = str.format("%s/%s-%s_shard-%03d.txt" %
                       (path, sequenceStart, sequenceEnd, shard))
      gcs._copy2(file, dst)
      if local:
        url = "http://localhost:8080/_ah/gcs" + dst
        logging.info("Output file available here: %s", url)
      shard += 1

    if local:
      logging.info("Genomics pipeline completed. Output files listed above.")
    else:
      url = "https://storage.cloud.google.com" + path
      logging.info("Genomics pipeline completed. Results: %s", url)


class PipelineConsolidateOutput(base_handler.PipelineBase):
  """A pipeline to process the result of the MapReduce job.

  Args:
    raw_coverage_data: the raw coverage data that is to be consolidated.
  """

  def run(self, readsetId, sequenceName, sequenceStart, sequenceEnd,
          raw_coverage_data):
    bucket = get_bucket_name()
    #logging.debug("Got %d raw coverage data output files to consolidate.",
    #              len(raw_coverage_data))

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
    yield PipelineReturnConsolidatedResults(readsetId, sequenceName,
                                            sequenceStart, sequenceEnd, output)


class PipelineReturnConsolidatedResults(base_handler.PipelineBase):
  """A pipeline to process the result of the MapReduce job.

  Args:
    output: the blobstore location where the output of the job is stored
  """

  def run(self, readsetId, sequenceName, sequenceStart, sequenceEnd, output):
    #logging.debug('Number of output files: %d', len(output))
    file = output[0]

    # If you have a setting to copy it over, do so
    dir = os.environ['OUTPUT_DIRECTORY']
    if dir is not None:
      bucket = get_bucket_name()
      src = file
      dst = str.format("/%s/%s/%s_%s_%s-%s.txt" % (
        bucket, dir, str(readsetId), str(sequenceName), sequenceStart,
        sequenceEnd))
      gcs._copy2(src, dst)
      logging.info("Copied output file to: %s" % dst)
      file = dst

    if os.environ['SERVER_SOFTWARE'].startswith('Development'):
      url = "http://localhost:8080/_ah/gcs" + file
    else:
      url = "https://storage.cloud.google.com" + file
    logging.info("Genomics pipeline completed. Results: %s", url)

