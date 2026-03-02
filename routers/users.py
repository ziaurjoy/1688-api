
import os
import shutil
import secrets
from pathlib import Path
from bson import ObjectId
from datetime import datetime, timedelta, timezone

from typing import Annotated


from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Request

from database import db
from utils import users as user_utils
from models import users as users_models

from utils.users import generate_secret_key, hash_secret

from dotenv import load_dotenv
from models.users import ResetPasswordRequest
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

    _user = await db.User.insert_one(data)

    user_id = _user.inserted_id  # ✅ this is ObjectId

    await db.user_profile.insert_one({
        "user": user_id,  # no need to wrap again
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })


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

    # return {"message": "OTP verified successfully"}
    return {
        "title": "OTP Verified",
        "message": "Your identity has been successfully confirmed. You can now set a new password for your account."
    }



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

    return {
        "title": "Check Your Inbox",
        "message": f"We've sent a 6-digit verification code to {email.email}. Please enter it below to continue."
    }

    # return {"message": "OTP sent successfully"}



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
async def read_users_me(current_user: Annotated[users_models.ReadOnlyUser, Depends(user_utils.get_current_active_user)]) -> users_models.ReadOnlyUser:
    user_profile = await db.user_profile.find_one({"user": ObjectId(current_user["_id"])})
    current_user['profile'] = user_profile
    return current_user

@router.patch("/profile/edit/")
async def update_profile(
    profile: users_models.UserProfile,
    current_user: Annotated[users_models.ReadOnlyUser, Depends(user_utils.get_current_active_user)]
):
    filter_users = await db.user_profile.find_one({"user": ObjectId(current_user["_id"])})
    if not filter_users:
        user_obj = {
            "user": ObjectId(current_user["_id"]),
            "full_name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone,
            # "profile_picture": profile.profile_picture,
            "status": profile.status,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await db.user_profile.insert_one(user_obj)
        return {"message": "Profile created successfully"}

    # Update the user's profile in the database
    result = await db.user_profile.update_one(
        {"user": ObjectId(current_user["_id"])},
        {
            "$set": {
                "full_name": profile.full_name,
                "email": profile.email,
                "phone": profile.phone,
                # "profile_picture": profile.profile_picture,
                "status": profile.status,
                "updated_at": datetime.utcnow()
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found or not updated")

    return {"message": "Profile updated successfully"}




# Create a directory for uploads if it doesn't exist
UPLOAD_DIR = Path("assets/profile_pics")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.patch("/profile/picture/edit/")
async def update_profile(
    request: Request,
    current_user: Annotated[dict, Depends(user_utils.get_current_active_user)],
    profile_picture: UploadFile = File(...) # This captures the binary file
):
    user_id = ObjectId(current_user["_id"])

    # 1. Create a unique filename
    file_extension = profile_picture.filename.split(".")[-1]
    file_name = f"{user_id}_{int(datetime.utcnow().timestamp())}.{file_extension}"
    file_path = UPLOAD_DIR / file_name

    # 2. Save the file to your local disk
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(profile_picture.file, buffer)

    # 3. Save the PATH string to MongoDB
    # Using an upsert logic to handle both "Create" and "Update" cases at once
    now = datetime.utcnow()
    base_url = str(request.base_url).rstrip("/")
    relative_path = f"{base_url}/assets/profile_pics/{file_name}"

    await db.user_profile.update_one(
        {"user": user_id},
        {
            "$set": {
                "profile_picture": relative_path,
                "updated_at": now
            },
            "$setOnInsert": {
                "user": user_id,
                "created_at": now,
                "full_name": current_user.get("full_name"), # Default from user account
                "status": True
            }
        },
        upsert=True
    )

    return {"message": "Profile picture updated", "url": relative_path}




@router.get("/secret/generate/")
async def secret_api_key(
    current_user: Annotated[dict, Depends(user_utils.get_current_active_user)]
):
    # Ensure current_user["_id"] is converted to ObjectId correctly
    try:
        user_id = ObjectId(current_user["_id"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    # 1. Verify subscription
    user_sub = await db.user_subscription.find_one({"user_id": user_id})
    if not user_sub:
        raise HTTPException(status_code=403, detail="Active subscription required")

    # 2. Generate new keys
    raw_secret = generate_secret_key()
    app_key = secrets.token_hex(8)
    hashed_secret = hash_secret(raw_secret)

    # Use timezone-aware UTC (utcnow is deprecated in newer Python versions)
    now = datetime.now(timezone.utc)

    # 3. Atomic Upsert
    # Note: Ensure the filter field "user_id" matches your DB schema
    result = await db.APICredential.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "app_key": app_key,
                "secret_key_hash": hashed_secret,
                "status": "active",
                "updated_at": now
            },
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": now
            }
        },
        upsert=True
    )

    # Log for debugging - if modified_count + upserted_id == 0, something is wrong
    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")

    # 4. Return the RAW secret
    return {
        "app_key": app_key,
        "secret_key": hashed_secret,
        "notice": "Store this secret safely. It will not be shown again."
    }



@router.get("/get-secret/")
async def get_secret_api_key(
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ]
):

    # is_secret = await db.APICredential.find_one({"user": ObjectId(current_user["_id"])})
    is_secret = await db.APICredential.find_one({"user_id": ObjectId(current_user["_id"])})

    if not is_secret:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return {
        "app_key": is_secret.get('app_key'),
        "secret_key": is_secret.get('secret_key_hash')
    }



@router.get("/api-uses/")
async def api_uses(
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ]
):
    try:
        # Safely get the user_id
        user_id = ObjectId(current_user["_id"])
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid User ID")

    query = db.api_hits.find({"user_id": user_id})

    data = []
    async for item in query:
        item["id"] = str(item.pop("_id"))
        item["user_id"] = str(item["user_id"])

        for key, value in item.items():
            if isinstance(value, ObjectId):
                item[key] = str(value)

        data.append(item)

    return { "data": data }



@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    # 1. Normalize Input
    _email = request.email.strip().lower()
    _otp = request.otp.strip()

    # 2. Verify OTP exists and is unused
    otp_record = await db.OTP.find_one({
        "email": _email,
        "otp": _otp,
        "verify": True
    })

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP or request already processed"
        )

    # 3. Handle Timezone Awareness (Fixes the TypeError)
    expire_time = otp_record.get("expire")

    # If it's a string, convert it; if it's already a datetime, ensure it's aware
    if isinstance(expire_time, str):
        expire_time = datetime.fromisoformat(expire_time)

    if expire_time.tzinfo is None:
        expire_time = expire_time.replace(tzinfo=timezone.utc)

    # Compare aware vs aware
    if expire_time < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired"
        )

    # 4. Update the User Password
    # Note: We filter ONLY by email here, as OTP lives in the OTP collection
    new_hashed_password = user_utils.get_password_hash(request.new_password)

    user_update = await db.User.update_one(
        {"email": _email},
        {
            "$set": {
                "password": new_hashed_password,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if user_update.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 5. Mark OTP as used (Invalidate)
    await db.OTP.update_one(
        {"_id": otp_record["_id"]},
        {"$set": {"verify": True, "used_at": datetime.now(timezone.utc)}}
    )

    return {
        "title": "Password Reset Successful",
        "message": "Your account security has been updated. You can now log in with your new password."
    }
