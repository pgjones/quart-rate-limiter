.. _quickstart:

Quickstart
==========

HTTP Routes
-----------

Quart-Rate-Limiter is used by associating it with an app and then decorating
routes you'd like to rate limit,

.. code-block:: python

   from datetime import timedelta
   from quart import Quart
   from quart_rate_limiter import RateLimiter, rate_limit

   app = Quart(__name__)
   rate_limiter = RateLimiter(app)

   @app.route('/')
   @rate_limit(1, timedelta(seconds=10))
   async def handler():
        return "Hello World!"

WebSocket Connections
---------------------

Quart-Rate-Limiter also supports rate limiting WebSocket connections:

.. code-block:: python

   from quart import websocket
   from quart_rate_limiter import WebSocketRateLimiter, WebSocketRateLimitException

   @app.websocket('/ws')
   async def websocket_endpoint():
       ratelimit = WebSocketRateLimiter(times=1, seconds=5)

       await websocket.accept()
       while True:
           try:
               data = await websocket.receive()
               await ratelimit(websocket, context_key=data)  # context_key is optional
               await websocket.send(f"Echo: {data}")
           except WebSocketRateLimitException:
               await websocket.send("Rate limited! Please slow down.")
