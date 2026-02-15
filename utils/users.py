
import os
import random
import requests
import secrets
import hashlib
from typing import Annotated
from fastapi.encoders import jsonable_encoder
from datetime import datetime, timedelta, timezone, timedelta

import jwt
from pwdlib import PasswordHash
from jwt.exceptions import InvalidTokenError

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from database import db
from models import users as users_models

from dotenv import load_dotenv
load_dotenv()



# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")



def hash_secret(secret: str):
    return hashlib.sha256(secret.encode()).hexdigest()

def generate_otp():
    return str(random.randint(100000, 999999))

def expire_token(minutes=5):
    return datetime.utcnow() + timedelta(minutes=minutes)


def generate_app_key():
    return "pub_" + secrets.token_urlsafe(16)

def generate_secret_key():
    return secrets.token_urlsafe(40)


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)

async def get_user(db, email):
    user = await db.User.find_one({'email': email})
    return user

def authenticate_user(user, password):
    if not user:
        return False
    if not verify_password(password, user['password']):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = users_models.TokenData(email=email)
    except InvalidTokenError:
        raise credentials_exception
    user = await get_user(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: Annotated["users_models.User", Depends(get_current_user)]):
    if current_user['disabled']:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user



async def fiend_credentials(requests):

    headers = dict(requests.headers)
    headers_dict = dict(headers)

    app_key = headers_dict.get("app-key")
    secret_key = headers_dict.get("secret-key")

    if not app_key or not secret_key:
        raise HTTPException(401, "Missing API credentials")

    app_key = app_key.strip()
    secret_key = secret_key.strip()

    credential = await db.APICredential.find_one({
        "app_key": app_key,
        "secret_key_hash": secret_key
    })

    if not credential:
        raise HTTPException(401, "Invalid API credentials")

    user = credential.get('user')

    return user


async def count_api_hit(endpoint: str, user):
    # Find existing record
    count_obj = await db.APIHit.find_one({"endpoint": endpoint, "user": user})

    if not count_obj:
        # Create new record
        _count_obj = {
            "endpoint": endpoint,
            "user": user,
            "total_hits": 1,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        data = await db.APIHit.insert_one(_count_obj)
        return data

    # Increment hits
    data = await db.APIHit.update_one(
        {"endpoint": endpoint, "user": user},
        {
            "$inc": {"total_hits": 1},  # increment by 1
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return data