import os
from typing import Annotated
from datetime import datetime, timedelta

from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, HTTPException, Depends, HTTPException, status

from database import db
from utils import users as user_utils
from models import users as users_models

from utils.users import generate_app_key, generate_secret_key, hash_secret

from dotenv import load_dotenv
load_dotenv()

# openssl rand -hex 32
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))


router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/registration")
async def registration(user: users_models.User):

    data = jsonable_encoder(user)

    # ✅ Hash the password before saving
    data["password"] = user_utils.get_password_hash(data["password"])

    _email = user.email
    fiend_user= await db.OTP.find_one({"email":_email})

    if fiend_user:

        _otp_data = {
            "email": data["email"],
            "otp": user_utils.generate_otp(),
            "verify": False,
            "expire": user_utils.expire_token(),        # Make sure this returns a datetime, not a function
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        # Replace the entire document
        await db.OTP.replace_one(
            {"email": _otp_data["email"]},  # Filter by email
            _otp_data,                      # Full new document
            upsert=True                      # Insert if not exists
        )

        return {
            "message": "Registration Successfully Done",
        }

    await db.User.insert_one(data)

    _otp_data = {
        "email": data["email"],   # ✅ fixed
        "otp": user_utils.generate_otp(),
        "verify": False,
        "expire": user_utils.expire_token(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    otp_data = jsonable_encoder(_otp_data)

    # ✅ Insert OTP
    await db.OTP.insert_one(otp_data)

    return {"message": "Registration Successfully Done"}




@router.post("/otp-verify")
async def otp_verify(otp: users_models.OTP):

    find_otp = await db.OTP.find_one({
        "email": otp.email,
        "otp": str(otp.otp)
    })

    if not find_otp:
        raise HTTPException(
            status_code=404,
            detail="Invalid OTP"
        )
    expire_time = datetime.fromisoformat(find_otp["expire"])
    # Optional: Expiry Check
    if find_otp.get("expire") and expire_time < datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="OTP expired"
        )


    # Replace the entire document
    await db.OTP.update_one(
        {
            "email": otp.email,
            "otp": str(otp.otp)
        },
        {
            "$set": {
                "verify": True,
                "updated_at": datetime.utcnow()
            }
        }
    )

    await db.User.update_one(
        {"email": otp.email},
        {
            "$set": {
                "disabled": False,
                "updated_at": datetime.utcnow()
            }
        }
    )

    return {"message": "OTP verified successfully"}



@router.post("/send-otp")
async def send_otp(email: users_models.SendOTPRequest):
    user = await db.User.find_one({'email': email.email})

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    _otp_data = {
        "email": email.email,   # ✅ fixed
        "otp": user_utils.generate_otp(),
        "verify": False,
        "expire": user_utils.expire_token(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    otp_data = jsonable_encoder(_otp_data)

    # ✅ Insert OTP
    await db.OTP.insert_one(otp_data)

    return {"message": "OTP sent successfully"}



@router.post("/token")
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> users_models.Token:
    user = await db.User.find_one({'email': form_data.username})
    user = user_utils.authenticate_user(user, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = user_utils.create_access_token(
        data={"sub": user['email']}, expires_delta=access_token_expires
    )

    api_credential = await db.APICredential.find_one({'user': user})

    del user["password"]


    if api_credential:
        return users_models.Token(access_token=access_token, user=user, api_credential=api_credential, token_type="bearer")

    return users_models.Token(access_token=access_token, user=user, token_type="bearer")



@router.get("/me/")
async def read_users_me(current_user: Annotated[users_models.User, Depends(user_utils.get_current_active_user)]) -> users_models.User:
    return current_user



@router.get("/secret/")
async def secret_api_key(
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ]
):
    is_secret = await db.APICredential.find_one({"user": current_user})

    if is_secret:
        app_key = generate_app_key()
        secret_key = generate_secret_key()

        doc = {
            "user": current_user,
            "app_key": app_key,
            "secret_key_hash": hash_secret(secret_key),
            "status": "active",
            "updated_at": datetime.utcnow()
        }

        await db.APICredential.replace_one(
            {"user": current_user},
            doc,   # ✅ FIXED
            upsert=True
        )

        return {
            "app_key": app_key,
            "secret_key": secret_key
        }


    app_key = generate_app_key()
    secret_key = generate_secret_key()

    doc = {
        "user": current_user,   # ✅ Correct
        "app_key": app_key,
        "secret_key_hash": hash_secret(secret_key),
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    await db.APICredential.insert_one(doc)

    return {
        "app_key": app_key,
        "secret_key": secret_key
    }



@router.get("/get-secret/")
async def get_secret_api_key(
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ]
):
    is_secret = await db.APICredential.find_one({"user": current_user})

    if not is_secret:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return {
        "app_key": is_secret.get('app_key'),
        "secret_key": is_secret.get('secret_key_hash')
    }


