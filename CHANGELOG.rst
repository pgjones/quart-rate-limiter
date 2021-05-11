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
