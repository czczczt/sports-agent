"""Модуль аутентификации и авторизации на PostgreSQL и Argon2 (SPEC v1.3).

Поддерживает роли:
- user (сотрудник)
- captain (капитан вида спорта)
- admin (администратор)

Пользователи хранятся в таблице PostgreSQL `app_user`, пароли захэшированы через Argon2.
При блокировке или статусе спортсмена `not_employee` вход в сервис запрещён.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status

from app.config import AUTH_SECRET_KEY
from app.models import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.modules.auth.dependencies import AuthServiceDep

router = APIRouter(prefix="/auth", tags=["auth"])

# Секрет для подписи токенов и время жизни
SECRET_KEY = (AUTH_SECRET_KEY or secrets.token_hex(32)).encode("utf-8")
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
    payload_raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")
    signature = hmac.new(
        SECRET_KEY, payload_raw.encode("utf-8"), hashlib.sha256
    ).digest()
    sig_raw = base64.urlsafe_b64encode(signature).decode("utf-8")
    return f"{payload_raw}.{sig_raw}"


def _verify_token_payload(token: str) -> dict | None:
    """Проверяет криптографическую подпись и срок действия токена."""
    if not token or token in _REVOKED_TOKENS:
        return None

    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_raw, sig_raw = parts
        expected_sig = hmac.new(
            SECRET_KEY, payload_raw.encode("utf-8"), hashlib.sha256
        ).digest()
        actual_sig = base64.urlsafe_b64decode(sig_raw.encode("utf-8"))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        data = json.loads(
            base64.urlsafe_b64decode(payload_raw.encode("utf-8")).decode("utf-8")
        )
        if data.get("exp", 0) < int(time.time()):
            return None

        return data
    except (ValueError, TypeError, KeyError, binascii.Error):
        return None


def _extract_token_from_header_or_cookie(
    authorization: str | None = Header(None),
    auth_token: str | None = Cookie(None),
) -> str | None:
    """Извлекает токен из заголовка Authorization (Bearer) или куки auth_token."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if auth_token:
        return auth_token.strip()
    return None


async def get_optional_current_user(
    conn: AuthServiceDep,
    token: str | None = Depends(_extract_token_from_header_or_cookie),
) -> UserOut | None:
    """Возвращает текущего пользователя или None, если запрошена гостевая сессия."""
    if not token:
        return None
    try:
        return await get_current_user(token=token, conn=conn)
    except HTTPException:
        return None


async def get_current_user(
    conn: AuthServiceDep,
    token: str | None = Depends(_extract_token_from_header_or_cookie),
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
    user_row = await conn.user_by_username(username)
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
        emp_status = await conn.athlete_employee_status(user_row["athlete_id"])
        if emp_status == "not_employee":
            await conn.block_user(user_row["id"])
            await conn.commit()
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
OptionalUserDep = Annotated[UserOut | None, Depends(get_optional_current_user)]


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
    conn: AuthServiceDep,
    credentials: LoginRequest,
    response: Response,
) -> AuthResponse:
    """Аутентификация по логину и паролю из базы данных PostgreSQL через Argon2."""
    user_row = await conn.login_user(credentials.username, credentials.username)
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        await asyncio.to_thread(
            _HASHER.verify, user_row["password_hash"], credentials.password
        )
    except (VerificationError, InvalidHashError):
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
        emp_status = await conn.login_employee_status(user_row["athlete_id"])
        if emp_status == "not_employee":
            await conn.block_login_user(user_row["id"])
            await conn.commit()
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
    token: str | None = Depends(_extract_token_from_header_or_cookie),
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    conn: AuthServiceDep,
    data: RegisterRequest,
):
    """
    Подача заявки на регистрацию/доступ (SPEC v1.3 §3.1, §8.6).
    Создаёт запись app_user со статусом 'pending' до подтверждения капитаном или администратором.
    """
    # Проверка уникальности логина и email
    existing = await conn.registration_exists(data.username, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким логином или email уже существует",
        )

    pwd_hash = await asyncio.to_thread(_HASHER.hash, data.password)
    display_name = f"{data.last_name} {data.first_name}".strip()

    parsed_birth_date = None
    if data.birth_date:
        from datetime import date

        try:
            parsed_birth_date = date.fromisoformat(data.birth_date)
        except ValueError:
            parsed_birth_date = None

    row = await conn.create_registration(
        data.username,
        data.email,
        pwd_hash,
        display_name,
        data.first_name,
        data.last_name,
        data.middle_name,
        parsed_birth_date,
        data.city,
        data.consent_version,
    )

    await conn.commit()
    return {
        "status": "pending",
        "message": "Заявка на доступ успешно подана и ожидает подтверждения капитаном или администратором",
        "user_id": row["id"],
    }


CaptainOrAdminDep = Annotated[UserOut, Depends(require_captain_or_admin)]
