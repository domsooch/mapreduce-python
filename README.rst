mapreduce-python
================

Getting started
---------------

This python client runs a `MapReduce on Google App Engine`_ that fetches a set
of data from the `Google Genomics API`_ and calculates read coverage.

.. _Google Genomics API: https://developers.google.com/genomics
.. _MapReduce on Google App Engine: https://developers.google.com/appengine/docs/python/dataprocessing

Running locally
~~~~~~~~~~~~~~~

To run with app engine, you'll need to `set up a Google App Engine environment
<https://developers.google.com/appengine/docs/python/gettingstartedpython27/introduction>`_.

You will also need to follow the `setup instructions
<https://developers.google.com/genomics>`_ to create a project in
the Google Cloud Console that has access to the Genomics API.

Once you have that project, you will need to create an OAuth Service Account
and convert the .p12 file that gets downloaded into a .pem file::

  cat privatekey.p12 | openssl pkcs12 -nodes -nocerts \
    -passin pass:notasecret | openssl rsa > private-key.pem

Then using the email address associated with the Service Account you created,
run the dev app server as follows::

  dev_appserver.py --appidentity_private_key_path private-key.pem \
    --appidentity_email_address XXX@developer.gserviceaccount.com

Without this setup, the Genomics API will return ``Invalid Credentials``.

Visit ``http://localhost:8080`` to use a simple UI for launching the MapReduce.


Deploying on app engine
~~~~~~~~~~~~~~~~~~~~~~~

To deploy on app engine, you'll need to make sure the ``API_KEY`` variable
in the ``app.yaml`` file is properly set.

The app engine project that you will be deploying to needs to have access to the
Genomics API. Once that's set up, go to the APIs & Auth -> Credentials page
in the Google Cloud Console.

In the bottom section called "Public API access", there should be an API key
that you can copy into the yaml file. Create a new key if there isn't one
present already.

For easy development, make sure your API key and the privatekey.12 file come
from the same project. Mismatches will cause exceptions.


Code layout
-----------

cloudstorage, `httplib2`_, `mapreduce`_, `oauth2client`_:
  these are all external libraries this sample depends on

genomicsapi.py:
  handles queries to the Genomics API. Includes helper methods to process
  API data. (like ``compute_coverage``)

input_reader.py:
  implements the App Engine MapReduce input reader class. Determines the shard
  split for a given query and uses ``genomicsapi`` to retrieve data for the
  pipeline.

pipeline.py:
  includes several MapReduce pipeline configurations. The one used by ``main.py``,
  ``PipelineGenerateCoverage``, computes Read coverage for a genomic region and
  the output ends up in GoogleCloudStorage (as many files).

main.py:
  provides a web interface (using templates/index.html) for starting up the
  MapReduce pipeline.

.. _oauth2client: https://code.google.com/p/google-api-python-client/wiki/OAuth2Client
.. _httplib2: https://github.com/jcgregorio/httplib2
.. _mapreduce: https://developers.google.com/appengine/docs/python/dataprocessing/mapreduce_library

Project status
--------------

Goals
~~~~~
* Provide a real world MapReduce example that uses the Genomics API (in python).
* Prove that a MapReduce is both feasible and a good idea for Genomics data.
  The resulting analysis should be useful.

Current status
~~~~~~~~~~~~~~
This code is nearing the end of active development. It is still receiving
performance improvements and other small tweaks.

It also might be more useful to switch the MapReduce to implement some sort of
Variant analysis rather than outputting Read coverage data. The former should
provide a better example of Reducing (which is fairly useless in coverage), and
should have a smaller final result (which makes it easier to consume).
