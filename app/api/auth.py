"""Модуль аутентификации и авторизации (пользователь и администратор).

Поддерживает вход по логину/паролю:
- user / user   -> роль "user"
- admin / admin -> роль "admin"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status

from app.models import AuthResponse, LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Секрет для подписи токенов и время жизни
SECRET_KEY = os.getenv("AUTH_SECRET_KEY", secrets.token_hex(32)).encode("utf-8")
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 дней

# Отозванные токены (после logout)
_REVOKED_TOKENS: set[str] = set()

# Предустановленные пользователи
USERS_DB = {
    "user": {
        "password": "user",
        "role": "user",
        "display_name": "Пользователь",
    },
    "admin": {
        "password": "admin",
        "role": "admin",
        "display_name": "Администратор",
    },
}


def _create_token(username: str, role: str, display_name: str) -> str:
    """Создаёт подписанный токен доступа (HMAC-SHA256)."""
    payload = {
        "sub": username,
        "role": role,
        "name": display_name,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
        "nonce": secrets.token_hex(8),
    }
    payload_raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8")
    signature = hmac.new(SECRET_KEY, payload_raw.encode("utf-8"), hashlib.sha256).digest()
    sig_raw = base64.urlsafe_b64encode(signature).decode("utf-8")
    return f"{payload_raw}.{sig_raw}"


def _verify_token(token: str) -> Optional[UserOut]:
    """Проверяет подпись, срок действия и отзыв токена."""
    if not token or token in _REVOKED_TOKENS:
        return None

    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_raw, sig_raw = parts
        expected_sig = hmac.new(SECRET_KEY, payload_raw.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_raw.encode("utf-8"))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        data = json.loads(base64.urlsafe_b64decode(payload_raw.encode("utf-8")).decode("utf-8"))
        if data.get("exp", 0) < int(time.time()):
            return None

        return UserOut(
            username=data["sub"],
            role=data["role"],
            display_name=data.get("name", data["sub"]),
        )
    except Exception:
        return None


def _extract_token_from_header_or_cookie(
    authorization: Optional[str] = Header(None),
    auth_token: Optional[str] = Cookie(None),
) -> Optional[str]:
    """Извлекает токен из заголовка Authorization (Bearer) или куки auth_token."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if auth_token:
        return auth_token.strip()
    return None


async def get_optional_current_user(
    token: Optional[str] = Depends(_extract_token_from_header_or_cookie),
) -> Optional[UserOut]:
    """Возвращает текущего пользователя или None, если запрошена гостевая сессия."""
    if not token:
        return None
    return _verify_token(token)


async def get_current_user(
    token: Optional[str] = Depends(_extract_token_from_header_or_cookie),
) -> UserOut:
    """Требует авторизованного пользователя, иначе 401."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[UserOut, Depends(get_current_user)]
OptionalUserDep = Annotated[Optional[UserOut], Depends(get_optional_current_user)]


async def require_admin(user: CurrentUserDep) -> UserOut:
    """Требует роль администратора, иначе 403."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуется роль администратора",
        )
    return user


AdminDep = Annotated[UserOut, Depends(require_admin)]


@router.post("/login", response_model=AuthResponse)
async def login(credentials: LoginRequest, response: Response) -> AuthResponse:
    """Аутентификация по логину и паролю.

    Успешный ответ возвращает access_token и данные пользователя,
    а также устанавливает HttpOnly cookie auth_token.
    """
    user_data = USERS_DB.get(credentials.username)
    if not user_data or user_data["password"] != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = UserOut(
        username=credentials.username,
        role=user_data["role"],
        display_name=user_data["display_name"],
    )
    token = _create_token(user.username, user.role, user.display_name)

    # Устанавливаем куку для поддержки автоматической авторизации в браузере
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )

    return AuthResponse(access_token=token, token_type="bearer", user=user)


@router.post("/logout")
async def logout(
    response: Response,
    token: Optional[str] = Depends(_extract_token_from_header_or_cookie),
) -> dict[str, str]:
    """Выход из системы: отзыв токена и очистка cookie."""
    if token:
        _REVOKED_TOKENS.add(token)
    response.delete_cookie(key="auth_token")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserDep) -> UserOut:
    """Возвращает профиль текущего авторизованного пользователя."""
    return user
