Configuring Quart-Rate-Limiter
==============================

The following configuration options are used by
Quart-Rate-Limiter. They should be set as part of the standard `Quart
configuration
<https://pgjones.gitlab.io/quart/how_to_guides/configuration.html>`_.

=========================== ============ ================
Configuration key           type         default
--------------------------- ------------ ----------------
QUART_RATE_LIMITER_ENABLED  bool         True
=========================== ============ ================

``QUART_RATE_LIMITER_ENABLED`` is most useful for testing as it
prevents rate limits, which may depend on test timing, from mistakenly
failing tests.
