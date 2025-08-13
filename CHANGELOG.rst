0.12.1 2025-08-13
-----------------

* Enforce timezone-aware datetimes fixing a bug with the migration to
  0.12.0.
* Bugfix round the retry times up.


0.12.0 2025-05-31
-----------------

* Support Valkey as an alternative store.
* Switch from utcnow to now(UTC) to remove deprecation warnings.

0.11.0 2024-12-24
-----------------

* Bugfix don't continually extend limits with blueprint/defaults.
* Support Python 3.13, drop Python 3.8.

0.10.0 2024-05-19
-----------------

* Add the ability to skip rate limits via a skip_function.

0.9.0 2023-10-07
----------------

* Officially support Python 3.12 drop Python 3.7.
* Support Quart 0.19 onwards.

0.8.0 2023-01-21
----------------

* Use redis rather than aioredis as the two have merged.
* Bugfix ensure the Content-Type header is present.
* Improve the typing for better type checking.
* Officially support Python 3.10, and Python 3.11.

0.7.0 2022-04-04
----------------

* Support an enabled flag, ``QUART_RATE_LIMITER_ENABLED`` to disable
  all rate limiting (meant for testing).

0.6.0 2021-09-04
----------------

* Support aioredis >= 2.0.
* Switch from remote_addr to access_route[0] for the remote key as the
  latter is correct when proxies are involved.

0.5.0 2021-05-11
----------------

* Support Quart 0.15 as the minimum version.

0.4.1 2021-04-10
----------------

* Bugfix cast Redis result to float.

0.4.0 2020-03-29
----------------

* Allow routes to be marked as rate exempt.
* Bugfix redis storage type.

0.3.0 2020-03-07
----------------

* Add optional default limits to be applied to all routes.
* Allow for an entire blueprint to be limited.
* Allow a list of limits when adding rate limits (rather than using
  multiple decorators).

0.2.0 2020-02-09
----------------

* Support Python 3.8.
* RateLimitExceeded now inherits from TooManyRequests in Quart.

0.1.0 2019-09-15
----------------

* Released initial alpha version.
