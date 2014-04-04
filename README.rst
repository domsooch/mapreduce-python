mapreduce-python
================

This sample is a work in progress.

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


Code layout
-----------

Under active development - coming soon!