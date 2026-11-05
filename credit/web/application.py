"""Sessions opaques côté serveur et passerelle ASGI de même origine."""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import BoundedSemaphore

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from credit.auth import authenticate
from credit.persistence import WebUser, WebSession
from credit.security.runtime import Limiter, audit, bounded_json

PASSWORDS = PasswordHasher()
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
COOKIE = "credit_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(user):
    path = os.getenv("CREDIT_AUTH_FILE")
    raw = Path(path).read_text() if path else os.getenv("CREDIT_AUTH_JSON", "")
    return digest(raw + str(user.revision) + user.password_hash)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(max_length=200)
    email: str = Field(max_length=300, pattern=r"^$|^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
    telephone: str = Field(max_length=100, pattern=r"^[0-9+(). /-]*$")


def create_web_app(database_url=None):
    from credit.api import create_app

    api = create_app(database_url)
    factory = api.state.session_factory
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.api = api
    app.state.session_factory = factory
    limiter = Limiter()
    password_slots = BoundedSemaphore(2)
    production = os.getenv("CREDIT_ENV", "local") == "production"
    origin = os.getenv("CREDIT_WEB_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    if production and not origin.startswith("https://"):
        raise RuntimeError("CREDIT_WEB_ORIGIN HTTPS obligatoire")
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv("CREDIT_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(
            ","
        ),
    )

    def session_user(request):
        raw = request.cookies.get(COOKIE, "")
        if not raw or len(raw) > 200:
            raise HTTPException(401, "Session expirée ; reconnectez-vous")
        with factory() as db:
            session = db.get(WebSession, digest(raw))
            user = db.get(WebUser, session.actor_id) if session else None
            now = datetime.now(timezone.utc)
            if (
                not session
                or not user
                or not user.enabled
                or utc(session.expires_at) <= now
                or utc(session.last_seen) + timedelta(minutes=30) <= now
                or not hmac.compare_digest(session.fingerprint, fingerprint(user))
            ):
                raise HTTPException(401, "Session expirée ; reconnectez-vous")
            actor = authenticate(request, configured_actor_id=user.actor_id)
            session.last_seen = now
            db.commit()
            return user, session, actor

    def csrf(request, session=None):
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "Origine non autorisée")
        if session is not None and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), session.csrf
        ):
            raise HTTPException(403, "Protection CSRF requise")

    def public_user(user, actor):
        return {
            **user.profile,
            "id": user.actor_id,
            "role": actor.role,
            "institution_id": actor.institution_id,
        }

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(
            {
                "detail": [
                    {"loc": e["loc"], "type": e["type"], "msg": e["msg"]} for e in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        try:
            if (
                production
                and request.url.scheme != "https"
                and path.startswith(("/auth/", "/api/"))
            ):
                raise HTTPException(400, "HTTPS requis")
            if path.startswith("/auth/"):
                limiter.check(("web", request.client.host if request.client else "local"), 120)
                await bounded_json(request)
            if path.startswith("/auth/") and path != "/auth/login":
                user, session, actor = session_user(request)
                request.state.web_user, request.state.web_session = user, session
                request.state.actor = actor
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    csrf(request, session)
            if path.startswith("/api/") and request.cookies.get(COOKIE):
                user, session, actor = session_user(request)
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    csrf(request, session)
                request.scope["credit.web_actor"] = actor
            response = await call_next(request)
        except HTTPException as exc:
            audit("web_access_denied", outcome=str(exc.status_code))
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        except Exception:
            audit("web_gateway_error", outcome="error")
            response = JSONResponse(
                {"detail": "Passerelle momentanément indisponible"}, status_code=503
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
            "frame-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
        )
        return response

    @app.post("/auth/login")
    def login(body: Login, request: Request):
        csrf(request)
        limiter.check(("login", request.client.host if request.client else "local"), 10)
        limiter.check(("login_user", digest(body.username.lower())), 10)
        from sqlalchemy import select

        with factory() as db:
            user = db.scalar(select(WebUser).where(WebUser.username == body.username.lower()))
            if not password_slots.acquire(blocking=False):
                raise HTTPException(429, "Service de connexion occupé")
            try:
                PASSWORDS.verify(user.password_hash if user else DUMMY_HASH, body.password)
            except (VerificationError, InvalidHashError):
                audit("web_login", outcome="denied")
                raise HTTPException(401, "Identifiants invalides") from None
            finally:
                password_slots.release()
            if not user or not user.enabled:
                raise HTTPException(401, "Identifiants invalides")
            actor = authenticate(request, configured_actor_id=user.actor_id)
            # Une connexion réussie remplace le cookie présenté, sans fixation de session.
            previous = db.get(WebSession, digest(request.cookies.get(COOKIE, "")))
            if previous:
                db.delete(previous)
            from sqlalchemy import delete

            db.execute(
                delete(WebSession).where(WebSession.expires_at <= datetime.now(timezone.utc))
            )
            active = db.scalars(
                select(WebSession)
                .where(WebSession.actor_id == user.actor_id)
                .order_by(WebSession.last_seen.desc())
            ).all()
            for stale in active[4:]:
                db.delete(stale)
            token = secrets.token_urlsafe(48)
            item = WebSession(
                digest=digest(token),
                actor_id=user.actor_id,
                csrf=secrets.token_urlsafe(32),
                fingerprint=fingerprint(user),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            )
            db.add(item)
            db.commit()
            response = JSONResponse({"user": public_user(user, actor)})
            response.set_cookie(
                COOKIE,
                token,
                httponly=True,
                secure=production,
                samesite="lax",
                max_age=28800,
                path="/",
            )
            audit("web_login", actor)
            return response

    @app.get("/auth/session")
    def current(request: Request):
        return {"user": public_user(request.state.web_user, request.state.actor)}

    @app.get("/auth/csrf")
    def csrf_token(request: Request):
        return {"token": request.state.web_session.csrf}

    @app.patch("/auth/profile")
    def update_profile(body: Profile, request: Request):
        with factory() as db:
            user = db.get(WebUser, request.state.actor.id)
            user.profile = body.model_dump()
            # Le profil n'altère pas les permissions ; renouveler l'empreinte de cette session.
            db.flush()
            item = db.get(WebSession, request.state.web_session.digest)
            item.fingerprint = fingerprint(user)
            db.commit()
            return {"user": public_user(user, request.state.actor)}

    @app.post("/auth/logout", status_code=204)
    def logout(request: Request):
        with factory() as db:
            item = db.get(WebSession, request.state.web_session.digest)
            if item:
                db.delete(item)
                db.commit()
        response = JSONResponse(None, status_code=204)
        response.delete_cookie(COOKIE, path="/", httponly=True, secure=production, samesite="lax")
        audit("web_logout", request.state.actor)
        return response

    @app.get("/health")
    def health():
        from sqlalchemy import text

        with factory() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.mount("/api", api)
    root = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if root.is_dir():
        static = StaticFiles(directory=root, html=True)

        class FrontendAndLegacy:
            async def __call__(self, scope, receive, send):
                # Compatibilité des clients techniques existants, toujours soumis au Bearer.
                legacy = (
                    "/individuals",
                    "/businesses",
                    "/assessments",
                    "/documents",
                    "/print-editions",
                    "/security",
                    "/docs",
                    "/redoc",
                    "/openapi.json",
                )
                if any(scope["path"] == p or scope["path"].startswith(p + "/") for p in legacy):
                    await api(scope, receive, send)
                else:
                    await static(scope, receive, send)

        app.mount("/", FrontendAndLegacy(), name="frontend")
    return app


app = create_web_app()
