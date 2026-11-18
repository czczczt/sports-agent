"""Модуль аутентификации и авторизации на PostgreSQL и Argon2 (SPEC v1.3).

Поддерживает роли:
- user (сотрудник)
- captain (капитан вида спорта)
- admin (администратор)

Пользователи хранятся в таблице PostgreSQL `app_user`, пароли захэшированы через Argon2.
При блокировке или статусе спортсмена `not_employee` вход в сервис запрещён.
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

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status

from app.config import DATABASE_URL
from app.db import AsyncPGConnection, get_db
from app.models import AuthResponse, LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Секрет для подписи токенов и время жизни
SECRET_KEY = os.getenv("AUTH_SECRET_KEY", secrets.token_hex(32)).encode("utf-8")
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 дней

# Отозванные токены (после logout)
_REVOKED_TOKENS: set[str] = set()
_HASHER = PasswordHasher()


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


def _verify_token_payload(token: str) -> Optional[dict]:
    """Проверяет криптографическую подпись и срок действия токена."""
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

        return data
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
    conn: AsyncPGConnection = Depends(get_db),
) -> Optional[UserOut]:
    """Возвращает текущего пользователя или None, если запрошена гостевая сессия."""
    if not token:
        return None
    try:
        return await get_current_user(token=token, conn=conn)
    except HTTPException:
        return None


async def get_current_user(
    token: Optional[str] = Depends(_extract_token_from_header_or_cookie),
    conn: AsyncPGConnection = Depends(get_db),
) -> UserOut:
    """Требует авторизованного пользователя, проверяя статус в PostgreSQL (иначе 401/403)."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _verify_token_payload(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload["sub"]
    user_row = await conn.fetchrow(
        "SELECT id, username, role, status, display_name, athlete_id FROM app_user WHERE username = ?",
        username,
    )
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверка статуса учетной записи
    if user_row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ закрыт: учётная запись заблокирована или ожидает подтверждения",
        )

    # Проверка статуса связанного спортсмена (авто-блок при not_employee)
    if user_row["athlete_id"]:
        emp_status = await conn.fetchval(
            "SELECT employee_status FROM athlete WHERE id = ?",
            user_row["athlete_id"],
        )
        if emp_status == "not_employee":
            await conn.execute("UPDATE app_user SET status = 'blocked' WHERE id = ?", user_row["id"])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ закрыт: статус сотрудника снят (not_employee)",
            )

    return UserOut(
        id=user_row["id"],
        username=user_row["username"],
        role=user_row["role"],
        status=user_row["status"],
        display_name=user_row["display_name"] or user_row["username"],
        athlete_id=user_row["athlete_id"],
    )


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


async def require_captain_or_admin(user: CurrentUserDep) -> UserOut:
    """Требует роль капитана или администратора, иначе 403."""
    if user.role not in ("captain", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуется роль капитана или администратора",
        )
    return user


AdminDep = Annotated[UserOut, Depends(require_admin)]


@router.post("/login", response_model=AuthResponse)
async def login(
    credentials: LoginRequest,
    response: Response,
    conn: AsyncPGConnection = Depends(get_db),
) -> AuthResponse:
    """Аутентификация по логину и паролю из базы данных PostgreSQL через Argon2."""
    user_row = await conn.fetchrow(
        "SELECT id, username, password_hash, role, status, display_name, athlete_id FROM app_user WHERE username = ? OR email = ?",
        credentials.username,
        credentials.username,
    )
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        _HASHER.verify(user_row["password_hash"], credentials.password)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверка статуса пользователя
    if user_row["status"] == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ваша заявка на регистрацию находится на рассмотрении",
        )
    if user_row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ закрыт: учётная запись заблокирована",
        )

    # Проверка статуса связанного спортсмена (авто-блок при not_employee)
    if user_row["athlete_id"]:
        emp_status = await conn.fetchval(
            "SELECT employee_status FROM athlete WHERE id = ?",
            user_row["athlete_id"],
        )
        if emp_status == "not_employee":
            await conn.execute("UPDATE app_user SET status = 'blocked' WHERE id = ?", user_row["id"])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ закрыт: статус сотрудника снят (not_employee)",
            )

    user = UserOut(
        id=user_row["id"],
        username=user_row["username"],
        role=user_row["role"],
        status=user_row["status"],
        display_name=user_row["display_name"] or user_row["username"],
        athlete_id=user_row["athlete_id"],
    )
    token = _create_token(user.username, user.role, user.display_name)

    # Устанавливаем куку
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
