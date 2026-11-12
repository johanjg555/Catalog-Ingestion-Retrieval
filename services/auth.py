from datetime import datetime, timedelta, timezone
from typing import Annotated
import asyncpg

import jwt
from fastapi import Depends,HTTPException, status,Security
from fastapi.security import OAuth2PasswordBearer,SecurityScopes
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from pwdlib import PasswordHash
from schema.authSchema import TokenData, UserInDB, User
from core.config import settings
from db.pool import get_pool
import uuid



password_hash = PasswordHash.recommended()

DUMMY_HASH = password_hash.hash("dummypassword")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token",
                                    scopes={"me":"Information about user",
                                            "upload":"Upload csv file"})



def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)


async def get_user(pool:asyncpg.Pool, username: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
            return UserInDB(**user) if user else None

async def authenticate_user(pool:asyncpg.Pool, username: str, password: str):
    user = await get_user(pool, username)
    if not user:
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    to_encode.update({"type":"access"})
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt



def create_refresh_token(data: dict, expires_delta: timedelta):
    jti = str(uuid.uuid4())

    to_encode = data.copy()
    to_encode.update({
        "type": "refresh",
        "jti": jti
    })

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire})

    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return token,jti,expire

async def get_current_user(security_scopes: SecurityScopes,
                            token: Annotated[str, Depends(oauth2_scheme)],
                            pool:Annotated[asyncpg.Pool,Depends(get_pool)]
                            ):
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type: Access token required",
            )

        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        scope: str = payload.get("scope", "")
        token_scopes = scope.split(" ")
        token_data = TokenData(scopes=token_scopes, username=username)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": authenticate_value},
        )
    except (jwt.PyJWTError, ValidationError):
        raise credentials_exception

    user = await get_user(pool=pool, username=token_data.username)
    if user is None:
        raise credentials_exception

    for scopes in security_scopes.scopes:
        if scopes not in token_data.scopes:
            raise  HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )
    return user



async def get_current_active_user(
    current_user: Annotated[User, Security(get_current_user,scopes=["me"])],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user