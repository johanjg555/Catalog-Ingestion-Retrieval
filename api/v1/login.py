from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm

from services.auth import authenticate_user,create_access_token,create_refresh_token

import jwt
from datetime import timedelta
from fastapi import APIRouter,HTTPException,status,Depends,Response,Request
from core.config import settings

from schema.authSchema import User,Token,user_form
from services.auth import get_current_active_user,get_password_hash
from db.register import check_and_create_table
from db.pool import get_pool
from datetime import datetime,timezone
import asyncpg

login_router = APIRouter(prefix="/api/v1", tags=["login"])


@login_router.post("/register")
async def register(user: Annotated[user_form, Depends()],pool:Annotated[asyncpg.Pool,Depends(get_pool)])   :
    username=user.username
    password=get_password_hash(user.password)
    email=user.email
    
    await check_and_create_table(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT username FROM users WHERE username=$1",
                user.username
            )
            if existing:
                return {"error": "User already exists"}

            await conn.execute(
                """
                INSERT INTO users (username, email, disabled, hashed_password)
                VALUES ($1, $2, $3, $4)
                """,
                username,
                email,
                False,
                password
            )

    return {"message": "User registered successfully"}

@login_router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response:Response,
    pool:Annotated[asyncpg.Pool,Depends(get_pool)]
) -> Token:
    user = await authenticate_user(pool, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(
        data={"sub": user.username, "scope": " ".join(form_data.scopes)},
        expires_delta=access_token_expires,
    )
    refresh_token,jti,expire = create_refresh_token(
        data={"sub": user.username, "scope": " ".join(form_data.scopes)},
        expires_delta=refresh_token_expires,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict"
    )

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO refresh_tokens (jti, username, expires_at, revoked)
            VALUES ($1, $2, $3, FALSE)
            """,
            jti,
            user.username,
            expire
        )

    return Token(access_token=access_token,token_type="bearer")


@login_router.post("/refresh")
async def refresh(request:Request,pool=Depends(get_pool)):
    token=request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        jti = payload.get("jti")
        async with pool.acquire() as conn:
            record = await conn.fetchrow(
                "SELECT revoked, expires_at FROM refresh_tokens WHERE jti=$1", 
                jti
            )

        if not record:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not recognized")
            
        if record["revoked"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
            
        if record["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired")


    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    scope = payload.get("scope", "")

    new_access_token = create_access_token(
        {
            "sub": user_id,
            "scope": scope
        },
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(access_token=new_access_token,token_type="bearer")





@login_router.post("/logout")
async def logout(response: Response, 
request:Request,
pool=Depends(get_pool)):
    
    token = request.cookies.get("refresh_token")
    
    if token:
        try:
            # Decode just to get the JTI for single-device logout
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")
            
            if jti:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE refresh_tokens SET revoked=TRUE WHERE jti=$1", 
                        jti
                    )
        except jwt.PyJWTError:
            pass # Even if token is malformed, we still want to clear the cookie below

    response.delete_cookie(
        key="refresh_token", 
        httponly=True, 
        secure=True, 
        samesite="strict"
    )
    
    return {"message": "Successfully logged out"}



@login_router.get("/users/me/")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user