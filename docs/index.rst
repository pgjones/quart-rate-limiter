:orphan:

.. title:: Quart-Rate-Limiter documentation

Quart-Rate-Limiter
==================

Quart-Rate-Limiter is an extension for `Quart
<https://github.com/pgjones/quart>`_ to allow for rate limits to be
defined and enforced on a per route basis. The 429 error response
includes a `RFC7231
<https://tools.ietf.org/html/rfc7231#section-7.1.3>`_ compliant
``Retry-After`` header and the successful responses contain headers
compliant with the `RateLimit Header Fields for HTTP
<https://tools.ietf.org/html/draft-polli-ratelimit-headers-00>`_ RFC
draft.

If you are,

 * new to Quart-Rate-Limiter then try the :ref:`quickstart`,
 * new to Quart then try the `Quart documentation
   <https://pgjones.gitlab.io/quart/>`_,

Quart-Rate-Limiter is developed on `GitHub
<https://github.com/pgjones/quart-rate-limiter>`_. If you come across
an issue, or have a feature request please open an `issue
<https://github.com/pgjones/quart-rate-limiter/issues>`_. If you want
to contribute a fix or the feature-implementation please do (typo
fixes welcome), by proposing a `merge request
<https://github.com/pgjones/quart-rate-limiter/merge_requests>`_. If
you want to ask for help try `on gitter
<https://gitter.im/python-quart/lobby>`_.

Tutorials
---------

.. toctree::
   :maxdepth: 2

   tutorials/index.rst

How to guides
-------------

.. toctree::
   :maxdepth: 2

   how_to_guides/index.rst

Discussion
----------

.. toctree::
   :maxdepth: 2

   discussion/index.rst

References
----------

.. toctree::
   :maxdepth: 2

   reference/index.rst
