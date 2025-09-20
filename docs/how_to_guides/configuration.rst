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
QUART_RATE_LIMITER_STORE    Store        None
=========================== ============ ================

``QUART_RATE_LIMITER_ENABLED`` is most useful for testing as it
prevents rate limits, which may depend on test timing, from mistakenly
failing tests.

``QUART_RATE_LIMITER_STORE`` is automatically set when you initialize
a ``RateLimiter`` instance with a custom store. This configuration value
is used by ``WebSocketRateLimiter`` to automatically detect and use the
same store for WebSocket rate limiting, ensuring consistency across HTTP
and WebSocket rate limiting in your application.

.. note::
   You should not set ``QUART_RATE_LIMITER_STORE`` manually. It is
   automatically managed by the ``RateLimiter`` during initialization.
