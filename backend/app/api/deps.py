from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.config import get_settings


class Reviewer:
    def __init__(self, name: str):
        self.name = name


def require_reviewer(x_reviewer_token: str | None = Header(None), x_reviewer_name: str | None = Header(None)) -> Reviewer:
    """DEMO reviewer protection (shared token + display name). NOT production-grade authentication:
    there are no per-user credentials, sessions, MFA or audit-grade identity proofing."""
    tok = get_settings().reviewer_token
    if not x_reviewer_token or not hmac.compare_digest(x_reviewer_token, tok):
        raise HTTPException(401, "Reviewer authentication required (demo token missing or invalid).")
    name = (x_reviewer_name or "").strip()
    if len(name) < 2:
        raise HTTPException(401, "Reviewer name required (X-Reviewer-Name header).")
    return Reviewer(name[:96])
