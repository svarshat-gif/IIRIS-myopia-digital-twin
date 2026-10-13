"""Single-worker request limits, security headers and durable access auditing."""
import hashlib
import hmac
import json
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.auth import decode_token
from app.db.database import SessionLocal
from app.db.models import AccessAudit, Patient
from sqlalchemy import select

log = logging.getLogger("iiris.requests")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"time": self.formatTime(record), "level": record.levelname,
                           "logger": record.name, "message": record.getMessage()})


class ControlsMiddleware(BaseHTTPMiddleware):
    # Deliberately one process/worker on free hosts. Use shared DB/Redis limits before scaling.
    buckets = defaultdict(deque)

    def limited(self, key, limit, now):
        bucket = self.buckets[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return max(1, int(61 - (now - bucket[0])))
        bucket.append(now)
        return 0

    async def dispatch(self, request: Request, call_next):
        rid = uuid.uuid4().hex
        request.state.request_id = rid
        path = request.url.path
        ip = request.client.host if request.client else "unknown"
        ip_hash = hmac.new(settings.jwt_secret.encode(), ip.encode(), hashlib.sha256).hexdigest()
        started = time.monotonic()
        response = None
        group = "auth" if "/auth/" in path and request.method == "POST" else (
            "compute" if any(s in path for s in ("simulate", "simulator", "projection", "query", "evidence/search", "sensitivity")) else None)
        if settings.rate_limit_enabled and group:
            if len(self.buckets) > 10000:
                for k in list(self.buckets):
                    if not self.buckets[k] or started - self.buckets[k][-1] >= 60:
                        del self.buckets[k]
            retry = self.limited((group, ip_hash), 20 if group == "auth" else 30, started)
            header = request.headers.get("authorization", "")
            if header.startswith("Bearer "):
                try:
                    subject = decode_token(header[7:])["sub"]
                    retry = max(retry, self.limited((group, subject), 15 if group == "auth" else 20, started))
                except Exception:
                    pass
            if retry:
                response = JSONResponse({"detail": "Too many requests; try again shortly"}, 429,
                                        headers={"Retry-After": str(retry)})
        if response is None:
            total, chunks = 0, []
            async for chunk in request.stream():
                total += len(chunk)
                if total > settings.max_request_bytes:
                    response = JSONResponse({"detail": "Request body is too large"}, 413)
                    break
                chunks.append(chunk)
            if response is None:
                request._body = b"".join(chunks)
                response = await call_next(request)
        actor = getattr(request.state, "actor_id", None)
        sensitive = any(s in path for s in ("/patients", "/me/", "/fhir/", "/agent/query", "/agent/runs", "/admin/"))
        if sensitive:
            try:
                with SessionLocal() as db:
                    patient_id = getattr(request.state, "patient_id", None)
                    if not patient_id and actor and "/me/" in path:
                        patient_id = db.scalar(select(Patient.patient_id).where(Patient.owner_user_id == actor).limit(1))
                    db.add(AccessAudit(actor_id=actor, patient_id=patient_id, action=request.method,
                                       resource=path[:255], status_code=response.status_code,
                                       ip_hash=ip_hash, request_id=rid))
                    db.commit()
            except Exception:
                log.exception("Access audit persistence failed")
                response = JSONResponse({"detail": "Access audit unavailable"}, 503)
        response.headers.update({"X-Request-ID": rid, "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cache-Control": "no-store"})
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        log.info(json.dumps({"request_id": rid, "method": request.method,
                            "route": getattr(request.scope.get("route"), "path", "unmatched"),
                            "status": response.status_code, "duration_ms": round((time.monotonic() - started) * 1000)}))
        return response
