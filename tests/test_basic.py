from datetime import datetime, timedelta
from typing import List

import pytest
from quart import abort, Blueprint, jsonify, Quart, request, ResponseReturnValue

from quart_rate_limiter import (
    limit_blueprint,
    rate_exempt,
    rate_limit,
    RateLimit,
    RateLimitExceeded,
    RateLimiter,
    StatusLimit,
)


async def test_rate_limit(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/")
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    response = await test_client.get("/rate_limit/")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"


async def test_rate_limit_unique_keys(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/", scope_base={"client": ("127.0.0.1",)})
    assert response.status_code == 200
    response = await test_client.get("/rate_limit/", scope_base={"client": ("127.0.0.2",)})
    assert response.status_code == 200


@pytest.fixture(name="app_default_limit")
def _app_default_limit() -> Quart:
    app = Quart(__name__)

    @app.route("/")
    async def index() -> ResponseReturnValue:
        return ""

    @app.route("/exempt")
    @rate_exempt
    async def exempt() -> ResponseReturnValue:
        return ""

    rate_limit = RateLimit(1, timedelta(seconds=2))
    RateLimiter(app, default_limits=[rate_limit])
    return app


async def test_default_rate_limits(app_default_limit: Quart, fixed_datetime: datetime) -> None:
    test_client = app_default_limit.test_client()
    response = await test_client.get("/")
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    response = await test_client.get("/")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"


async def test_rate_exempt(app_default_limit: Quart) -> None:
    test_client = app_default_limit.test_client()
    response = await test_client.get("/exempt")
    assert "RateLimit-Limit" not in response.headers
    assert "RateLimit-Remaining" not in response.headers
    assert "RateLimit-Reset" not in response.headers

    response = await test_client.get("/exempt")
    assert response.status_code == 200


async def test_rate_limit_skip_function(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/", headers={"X-Skip": "True"})
    assert response.status_code == 200
    response = await test_client.get("/rate_limit/", headers={"X-Skip": "True"})
    assert response.status_code == 200


@pytest.fixture(name="app_blueprint_limit")
def _app_blueprint_limit() -> Quart:
    app = Quart(__name__)

    blueprint = Blueprint("blue", __name__)

    @blueprint.route("/")
    async def index() -> ResponseReturnValue:
        return ""

    app.register_blueprint(blueprint)

    RateLimiter(app)
    limit_blueprint(blueprint, 1, timedelta(seconds=2))
    return app


async def test_blueprint_rate_limits(app_blueprint_limit: Quart, fixed_datetime: datetime) -> None:
    test_client = app_blueprint_limit.test_client()
    response = await test_client.get("/")
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    response = await test_client.get("/")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"


@pytest.fixture(name="app_not_found_limit")
def _app_not_found_limit() -> Quart:
    app = Quart(__name__)

    @app.route("/")
    async def index() -> ResponseReturnValue:
        return ""

    @app.route("/user/<id>")
    async def user(id: str) -> ResponseReturnValue:
        if id != "1":
            abort(404)
        return ""

    @app.route("/trailing/")
    async def trailing() -> ResponseReturnValue:
        return ""

    RateLimiter(
        app,
        status_limits=[
            StatusLimit("not_found", (404, 405), [RateLimit(1, timedelta(seconds=2))]),
        ],
    )
    return app


async def test_not_found_rate_limit(app_not_found_limit: Quart, fixed_datetime: datetime) -> None:
    test_client = app_not_found_limit.test_client()
    response = await test_client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    # A path never requested before shares the budget, otherwise a scanner
    # walking a wordlist would never repeat a key.
    response = await test_client.get("/also-missing")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"


async def test_not_found_limit_shared_with_aborted_routes(
    app_not_found_limit: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_not_found_limit.test_client()
    response = await test_client.get("/user/2")
    assert response.status_code == 404

    response = await test_client.get("/user/3")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"

    response = await test_client.get("/unrouted")
    assert response.status_code == 429


async def test_not_found_limit_leaves_routes_alone(
    app_not_found_limit: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_not_found_limit.test_client()
    assert (await test_client.get("/missing")).status_code == 404
    assert (await test_client.get("/missing")).status_code == 429

    # Exhausting the not-found budget must not lock a client out of the
    # routes that do exist.
    for _ in range(3):
        response = await test_client.get("/")
        assert response.status_code == 200
        response = await test_client.get("/user/1")
        assert response.status_code == 200


async def test_not_found_limit_unique_keys(
    app_not_found_limit: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_not_found_limit.test_client()
    response = await test_client.get("/missing", scope_base={"client": ("127.0.0.1",)})
    assert response.status_code == 404
    response = await test_client.get("/missing", scope_base={"client": ("127.0.0.2",)})
    assert response.status_code == 404


async def test_not_found_limit_method_not_allowed(
    app_not_found_limit: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_not_found_limit.test_client()
    assert (await test_client.post("/")).status_code == 405
    assert (await test_client.post("/")).status_code == 429


async def test_not_found_limit_ignores_redirects(
    app_not_found_limit: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_not_found_limit.test_client()
    for _ in range(3):
        response = await test_client.get("/trailing")
        assert response.status_code == 308


async def test_not_found_unlimited_by_default(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    for _ in range(3):
        response = await test_client.get("/missing")
        assert response.status_code == 404


@pytest.fixture(name="app_not_found_handler")
def _app_not_found_handler() -> Quart:
    app = Quart(__name__)

    @app.route("/user/<id>")
    async def user(id: str) -> ResponseReturnValue:
        abort(404)

    @app.errorhandler(429)
    async def handle_429(error: Exception) -> ResponseReturnValue:
        return jsonify({"detail": "Trop de requêtes", "path": request.path}), 429

    RateLimiter(
        app,
        status_limits=[
            StatusLimit("not_found", (404,), [RateLimit(1, timedelta(seconds=2))]),
        ],
    )
    return app


async def test_status_limit_uses_error_handler(
    app_not_found_handler: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_not_found_handler.test_client()
    assert (await test_client.get("/user/2")).status_code == 404

    # The rejection is decided after the view ran, so it must still reach
    # the app's own 429 handler rather than surface as a 500.
    response = await test_client.get("/user/3")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
    assert (await response.get_json())["path"] == "/user/3"


@pytest.fixture(name="app_status_limits")
def _app_status_limits() -> Quart:
    app = Quart(__name__)

    calls: List[str] = []
    app.calls = calls  # type: ignore[attr-defined]

    @app.route("/login", methods=["POST"])
    async def login() -> ResponseReturnValue:
        calls.append("login")
        abort(401)

    @app.route("/boom")
    async def boom() -> ResponseReturnValue:
        abort(503)

    @app.route("/ok")
    async def ok() -> ResponseReturnValue:
        return ""

    RateLimiter(
        app,
        status_limits=[
            StatusLimit("not_found", (404, 405), [RateLimit(2, timedelta(seconds=2))]),
            StatusLimit(
                "auth", (401, 403), [RateLimit(1, timedelta(seconds=2))], deny_early=True
            ),
            StatusLimit("server_error", range(500, 600), [RateLimit(1, timedelta(seconds=2))]),
        ],
    )
    return app


async def test_status_limit_on_refused_requests(
    app_status_limits: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_status_limits.test_client()
    response = await test_client.post("/login")
    assert response.status_code == 401

    response = await test_client.post("/login")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"


async def test_status_limit_deny_early_skips_the_view(
    app_status_limits: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_status_limits.test_client()
    assert (await test_client.post("/login")).status_code == 401
    assert (await test_client.post("/login")).status_code == 429
    assert (await test_client.post("/login")).status_code == 429

    # The point of deny_early is that the expensive view stops running
    # once the client is over budget.
    assert app_status_limits.calls == ["login"]  # type: ignore[attr-defined]

    # And that the denial is not confined to the requests that would be
    # charged, unlike the default.
    assert (await test_client.get("/ok")).status_code == 429


async def test_status_limit_predicate_and_range(
    app_status_limits: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_status_limits.test_client()
    assert (await test_client.get("/boom")).status_code == 503
    assert (await test_client.get("/boom")).status_code == 429


async def test_status_limits_are_independent(
    app_status_limits: Quart, fixed_datetime: datetime
) -> None:
    test_client = app_status_limits.test_client()
    # Spending the 5xx budget must not spend the not-found one.
    assert (await test_client.get("/boom")).status_code == 503
    assert (await test_client.get("/missing")).status_code == 404
    assert (await test_client.get("/missing")).status_code == 404
    assert (await test_client.get("/missing")).status_code == 429


async def test_status_limit_callable_status_codes(fixed_datetime: datetime) -> None:
    app = Quart(__name__)

    @app.route("/")
    async def index() -> ResponseReturnValue:
        return ""

    RateLimiter(
        app,
        status_limits=[
            StatusLimit(
                "client_error",
                lambda code: 400 <= code < 500,
                [RateLimit(1, timedelta(seconds=2))],
            ),
        ],
    )
    test_client = app.test_client()
    assert (await test_client.get("/missing")).status_code == 404
    assert (await test_client.post("/")).status_code == 429
    assert (await test_client.get("/")).status_code == 200


def test_status_limit_requires_limits() -> None:
    with pytest.raises(ValueError):
        StatusLimit("empty", (404,), [])


def _counting_app(**kwargs: object) -> Quart:
    """An app whose error handler records every time it is entered."""
    app = Quart(__name__)
    rendered: List[int] = []
    app.rendered = rendered  # type: ignore[attr-defined]

    @app.route("/user/<id>")
    async def user(id: str) -> ResponseReturnValue:
        abort(404)

    @app.errorhandler(404)
    @app.errorhandler(429)
    async def handle(error: Exception) -> ResponseReturnValue:
        # Stands in for restoring a session and rendering a template.
        rendered.append(error.code)  # type: ignore[attr-defined]
        return jsonify({"code": error.code}), error.code  # type: ignore[attr-defined]

    RateLimiter(
        app,
        status_limits=[StatusLimit("not_found", (404,), [RateLimit(1, timedelta(seconds=2))])],
        **kwargs,  # type: ignore[arg-type]
    )
    return app


async def test_unrouted_rejection_renders_once(fixed_datetime: datetime) -> None:
    app = _counting_app()
    test_client = app.test_client()

    assert (await test_client.get("/missing")).status_code == 404
    assert app.rendered == [404]  # type: ignore[attr-defined]

    # Routing has already failed when before_request runs, so the status
    # is known without dispatching and the 404 page is never built.
    response = await test_client.get("/other-missing")
    assert response.status_code == 429
    assert app.rendered == [404, 429]  # type: ignore[attr-defined]


async def test_routed_rejection_renders_twice_by_default(fixed_datetime: datetime) -> None:
    app = _counting_app()
    test_client = app.test_client()

    assert (await test_client.get("/user/2")).status_code == 404
    assert app.rendered == [404]  # type: ignore[attr-defined]

    # A route that aborts cannot be predicted, so its 404 is rendered
    # before the budget is known to be spent, then discarded.
    response = await test_client.get("/user/3")
    assert response.status_code == 429
    assert app.rendered == [404, 404, 429]  # type: ignore[attr-defined]


async def test_rejection_handler_replaces_the_discarded_render(fixed_datetime: datetime) -> None:
    async def cheap_429(error: RateLimitExceeded) -> ResponseReturnValue:
        return "", 429

    app = _counting_app(rejection_handler=cheap_429)
    test_client = app.test_client()

    assert (await test_client.get("/user/2")).status_code == 404
    response = await test_client.get("/user/3")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
    # The discarded 404 is unavoidable, the second render is not.
    assert app.rendered == [404, 404]  # type: ignore[attr-defined]


async def test_rejection_handler_leaves_route_limits_alone(fixed_datetime: datetime) -> None:
    async def cheap_429(error: RateLimitExceeded) -> ResponseReturnValue:
        return "cheap", 429

    app = Quart(__name__)

    @app.route("/")
    @rate_limit(1, timedelta(seconds=2))
    async def index() -> ResponseReturnValue:
        return ""

    @app.errorhandler(429)
    async def handle(error: Exception) -> ResponseReturnValue:
        return "branded", 429

    RateLimiter(app, rejection_handler=cheap_429)
    test_client = app.test_client()

    assert (await test_client.get("/")).status_code == 200
    # A legitimate client clicking twice hits a route limit, which raises
    # before dispatch and so still gets the app's own page.
    response = await test_client.get("/")
    assert response.status_code == 429
    assert (await response.get_data(as_text=True)) == "branded"
