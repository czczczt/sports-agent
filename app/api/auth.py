from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel

from app.config import (
    AUTH_SECRET_KEY,
    LOCKOUT_MINUTES,
    MAX_LOGIN_ATTEMPTS,
)
from app.core.email import send_password_reset_email
from app.models import (
    AuthResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    UserOut,
)
from app.modules.auth.dependencies import AuthServiceDep

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = (AUTH_SECRET_KEY or secrets.token_hex(32)).encode("utf-8")
TOKEN_TTL_SECONDS = 7 * 24 * 3600
_HASHER = PasswordHasher()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_token(username: str, role: str, display_name: str) -> str:
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
    if not token:
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
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if auth_token:
        return auth_token.strip()
    return None


async def get_optional_current_user(
    conn: AuthServiceDep,
    token: str | None = Depends(_extract_token_from_header_or_cookie),
) -> UserOut | None:
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

    if await conn.is_token_revoked(_token_hash(token)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия завершена (токен отозван)",
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

    if user_row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ закрыт: учётная запись заблокирована или ожидает подтверждения",
        )

    if user_row["athlete_id"]:
        emp_status = await conn.athlete_employee_status(user_row["athlete_id"])
        if emp_status == "not_employee":
            await conn.block_user(user_row["id"])
            await conn.log_audit(
                user_id=user_row["id"],
                action="auto_block_not_employee",
                entity="app_user",
                entity_id=user_row["id"],
            )
            await conn.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ закрыт: статус сотрудника снят (not_employee)",
            )

    captain_sports: list[str] = []
    if user_row["role"] == "captain":
        captain_sports = await conn.get_captain_sports(user_row["id"])
    elif user_row["role"] == "admin":
        captain_sports = ["run", "ski", "biathlon", "triathlon", "trail"]

    return UserOut(
        id=user_row["id"],
        username=user_row["username"],
        role=user_row["role"],
        status=user_row["status"],
        display_name=user_row["display_name"] or user_row["username"],
        athlete_id=user_row["athlete_id"],
        captain_sports=captain_sports,
    )


def check_captain_sport_scope(
    user: UserOut, sport: str | None, action_desc: str = "действие"
) -> None:
    if user.role == "admin":
        return
    if user.role != "captain":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуются права капитана или администратора",
        )
    effective = (sport or "run").lower()
    if effective not in [s.lower() for s in user.captain_sports]:
        sports_str = (
            ", ".join(user.captain_sports)
            if user.captain_sports
            else "нет назначенных видов"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Доступ запрещён: {action_desc} доступно только для видов спорта капитана ({sports_str})",
        )


CurrentUserDep = Annotated[UserOut, Depends(get_current_user)]
OptionalUserDep = Annotated[UserOut | None, Depends(get_optional_current_user)]


async def require_admin(user: CurrentUserDep) -> UserOut:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуется роль администратора",
        )
    return user


async def require_captain_or_admin(user: CurrentUserDep) -> UserOut:
    if user.role not in ("captain", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуется роль капитана или администратора",
        )
    return user


AdminDep = Annotated[UserOut, Depends(require_admin)]
CaptainOrAdminDep = Annotated[UserOut, Depends(require_captain_or_admin)]


class StatusResponse(BaseModel):
    status: str


class MessageResponse(StatusResponse):
    message: str


class RegistrationResponse(MessageResponse):
    user_id: int


@router.post("/login", response_model=AuthResponse)
async def login(
    conn: AuthServiceDep,
    credentials: LoginRequest,
    response: Response,
) -> AuthResponse:
    user_row = await conn.login_user(credentials.username, credentials.username)
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now_utc = datetime.now(UTC)
    if user_row["locked_until"] and user_row["locked_until"] > now_utc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись временно заблокирована из-за частых неудачных попыток входа. Попробуйте позже.",
        )

    try:
        await asyncio.to_thread(
            _HASHER.verify, user_row["password_hash"], credentials.password
        )
    except (VerificationError, InvalidHashError):
        updated = await conn.record_failed_login(
            user_row["id"],
            max_attempts=MAX_LOGIN_ATTEMPTS,
            lockout_minutes=LOCKOUT_MINUTES,
        )
        await conn.commit()
        if updated and updated["locked_until"] and updated["locked_until"] > now_utc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Превышено число попыток входа ({MAX_LOGIN_ATTEMPTS}). Доступ временно заблокирован на {LOCKOUT_MINUTES} минут.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if (user_row["failed_logins"] or 0) > 0 or user_row["locked_until"]:
        await conn.reset_failed_logins(user_row["id"])
        await conn.commit()

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

    if user_row["athlete_id"]:
        emp_status = await conn.login_employee_status(user_row["athlete_id"])
        if emp_status == "not_employee":
            await conn.block_login_user(user_row["id"])
            await conn.log_audit(
                user_id=user_row["id"],
                action="auto_block_not_employee",
                entity="app_user",
                entity_id=user_row["id"],
            )
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

    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )

    return AuthResponse(access_token=token, token_type="bearer", user=user)


@router.post("/logout", response_model=StatusResponse)
async def logout(
    conn: AuthServiceDep,
    response: Response,
    token: str | None = Depends(_extract_token_from_header_or_cookie),
) -> dict[str, str]:
    if token:
        payload = _verify_token_payload(token)
        exp_ts = payload.get("exp") if payload else int(time.time()) + TOKEN_TTL_SECONDS
        exp_dt = datetime.fromtimestamp(exp_ts, tz=UTC)
        await conn.revoke_token(_token_hash(token), exp_dt)
        await conn.commit()

    response.delete_cookie(key="auth_token")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserDep) -> UserOut:
    return user


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register(
    conn: AuthServiceDep,
    data: RegisterRequest,
):
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

    await conn.log_audit(
        user_id=row["id"],
        action="registration_request",
        entity="app_user",
        entity_id=row["id"],
        diff=json.dumps(
            {
                "username": data.username,
                "email": data.email,
                "city": data.city,
                "consent_version": data.consent_version,
            },
            ensure_ascii=False,
        ),
    )
    await conn.commit()

    return {
        "status": "pending",
        "message": "Заявка на доступ успешно подана и ожидает подтверждения капитаном или администратором",
        "user_id": row["id"],
    }


@router.post("/password-reset-request", response_model=MessageResponse)
async def request_password_reset(
    conn: AuthServiceDep,
    body: PasswordResetRequest,
):
    user_row = await conn.user_by_email(body.email)
    if user_row and user_row["status"] == "active":
        raw_token = secrets.token_urlsafe(32)
        thash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        await conn.create_password_reset_token(user_row["id"], thash, expires_at)
        await conn.log_audit(
            user_id=user_row["id"],
            action="password_reset_request",
            entity="app_user",
            entity_id=user_row["id"],
        )
        await conn.commit()
        await send_password_reset_email(body.email, raw_token)

    return {
        "status": "ok",
        "message": "Если указанный адрес зарегистрирован, ссылка для сброса пароля отправлена на почту",
    }


@router.post("/password-reset", response_model=MessageResponse)
async def confirm_password_reset(
    conn: AuthServiceDep,
    body: PasswordResetConfirm,
):
    thash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    reset_row = await conn.get_valid_reset_token(thash)
    if not reset_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недействительный или истёкший токен сброса пароля",
        )

    new_hash = await asyncio.to_thread(_HASHER.hash, body.new_password)
    await conn.update_user_password(reset_row["user_id"], new_hash)
    await conn.mark_reset_token_used(reset_row["id"])
    await conn.log_audit(
        user_id=reset_row["user_id"],
        action="password_reset_confirm",
        entity="app_user",
        entity_id=reset_row["user_id"],
    )
    await conn.commit()

    return {
        "status": "ok",
        "message": "Пароль успешно изменён. Теперь вы можете войти в систему с новым паролем.",
    }
