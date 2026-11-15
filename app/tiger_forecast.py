"""Remember a small browser forecast without storing it as an academic record."""

import os

from fastapi import Request
from fastapi.responses import Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import ValidationError

from models.tiger_planning import PlanningResult

COOKIE_NAME: str = "tiger_forecast"


def read_forecast(request: Request) -> PlanningResult | None:
    """Read a signed forecast belonging to this browser.

    Args:
        request: Request carrying the optional forecast cookie.

    Returns:
        A valid forecast, or None when missing, expired, or unavailable.
    """
    secret: str = os.getenv("SESSION_SECRET", "")
    value: str = request.cookies.get(COOKIE_NAME, "")
    if not secret or not value:
        return None
    try:
        data: object = URLSafeTimedSerializer(
            secret, salt="tiger-forecast"
        ).loads(value, max_age=86400)
        return PlanningResult.model_validate(data)
    except (BadSignature, ValidationError):
        return None


def save_forecast(
    request: Request, response: Response, result: PlanningResult
) -> None:
    """Save only the computed forecast when a signing secret is configured.

    Args:
        request: Request used to select the HTTPS cookie setting.
        response: HTML response that receives the browser cookie.
        result: Computed forecast; course names and raw inputs are not stored.
    """
    secret: str = os.getenv("SESSION_SECRET", "")
    if not secret:
        return
    value: str = URLSafeTimedSerializer(secret, salt="tiger-forecast").dumps(
        result.model_dump()
    )
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=86400,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
