import secrets
from typing import Annotated

from fastapi import Header, HTTPException

from app.core.config import get_settings


async def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if x_api_key is None or not secrets.compare_digest(x_api_key, get_settings().api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
