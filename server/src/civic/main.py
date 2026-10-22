"""FastAPI application entrypoint."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from civic import graph
from civic.ratelimit import LIMITS, RateLimiter
from civic.routes import admin, chat, health, instruments, search
from civic.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.oidc_issuer and not settings.admin_token:
        if settings.civic_environment == "dev":
            logging.getLogger(__name__).warning(
                "Admin routes are OPEN (dev environment, no OIDC issuer or admin token configured)."
            )
        else:
            logging.getLogger(__name__).error(
                "Admin routes are locked: production environment without admin auth configuration."
            )
    try:
        await graph.ensure_schema()
    except Exception:
        if settings.civic_environment == "prod":
            raise
        logging.getLogger(__name__).warning(
            "Neo4j unreachable at %s - starting in degraded mode; "
            "graph-backed routes will return errors until it is available.",
            settings.neo4j_uri,
        )
    yield
    await graph.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CivicGraph API",
        version="0.3.0",
        description="Grounded Q&A over municipal by-laws. Information, not legal advice.",
        lifespan=lifespan,
        docs_url="/docs",
    )

    limiter = RateLimiter()

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        limits = LIMITS.get(request.url.path)
        if limits is not None and request.method == "POST":
            ip = request.client.host if request.client else "unknown"
            ok, retry_after, remaining = limiter.check(ip, request.url.path, limits[0], limits[1])
            if not ok:
                return JSONResponse(
                    {
                        "type": "about:blank",
                        "title": "Too many requests",
                        "status": 429,
                        "code": "rate_limited",
                        "detail": f"Limit is {limits[0]} requests per minute.",
                    },
                    status_code=429,
                    media_type="application/problem+json",
                    headers={"Retry-After": str(retry_after)},
                )
            response = await call_next(request)
            response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
            return response
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_header(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or ("req_" + uuid.uuid4().hex[:12])
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Internal error",
                "status": 500,
                "code": "internal",
            },
            status_code=500,
        )

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    app.include_router(health.router)
    app.include_router(chat.router, prefix="/v1")
    app.include_router(search.router, prefix="/v1")
    app.include_router(instruments.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")

    return app


app = create_app()
