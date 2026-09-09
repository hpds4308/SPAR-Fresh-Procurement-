from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.errors import register_error_handlers
from app.core.rate_limit import limiter
from app.api.v1.router import api_router

configure_logging()

# Interactive docs (Swagger UI) and the raw OpenAPI schema hand anyone a
# complete map of every endpoint, including admin-only ones — useful in
# development, unnecessary attack-surface reconnaissance once the app is
# live. Every endpoint still enforces its own auth regardless of whether
# its shape is publicly documented, so this isn't a security boundary by
# itself — just removing free information a production deployment
# shouldn't be handing out. Enabled whenever APP_ENV isn't "production"
# (development, testing, or anything else left unset all keep docs on).
_docs_enabled = settings.APP_ENV != "production"

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url=f"{settings.API_V1_PREFIX}/docs" if _docs_enabled else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if _docs_enabled else None,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if _docs_enabled else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """
    A couple of headers that are always safe to send from the API itself,
    regardless of environment or reverse proxy. The rest of the standard
    security-header set (CSP, HSTS, X-Frame-Options, Referrer-Policy) is
    applied once, for both this API and the frontend, at the Caddy layer
    in production (see Caddyfile) — HSTS in particular would be actively
    wrong to send from here, since this app is reached directly over
    plain HTTP in local development with no Caddy in front of it at all.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "running", "docs": f"{settings.API_V1_PREFIX}/docs"}
