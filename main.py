
import os
import sys
from fastapi import FastAPI, Response, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv

load_dotenv()

# --- 1. Project Path & Imports ---
BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

script_dir = os.path.dirname(__file__)
upload_dir = os.path.join(script_dir, "")



if not os.path.exists(upload_dir):
    os.makedirs(upload_dir)

from fastapi_mongo_admin import mount_admin_app
from routers.products import router as product_router
from routers.users import router as users_router
from routers.subscription import router as subscription_router
from routers.payment import router as payment_router
from routers.invoice import router as invoice_router

from database import db


# Initialize App
app = FastAPI(title="FastAPI Mongo Admin Panel")

# --- 2. Database Dependency ---
async def get_database():
    return db

# --- 3. Middleware Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.68.118:3000",
        "http://localhost",
        "http://localhost:8080",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

admin_secret_token = os.getenv("ADMIN_SECRET_TOKEN")

# Protect the Admin UI and API via Middleware for global coverage
@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    # Only protect paths starting with /admin or /admin-ui
    if request.url.path.startswith("/admin"):
        # Exclude the login logic itself if it were under this prefix
        token = request.cookies.get("admin_access_token")
        if token !=admin_secret_token:
            # If browser request, redirect to login; else return 401
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse(url="/login")
            return Response(content="Unauthorized", status_code=401)


    return await call_next(request)

# --- 4. Authentication Routes ---
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <html>
    <body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; background:#f4f4f4;">
        <form action="/auth/login" method="post" style="padding:40px; border:1px solid #ccc; border-radius:10px; background:white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h2 style="margin-top:0;">Admin Login</h2>
            <input type="password" name="password" placeholder="Enter Token" required
                   style="padding:10px; display:block; margin-bottom:15px; width:100%; box-sizing:border-box;">
            <button type="submit" style="width:100%; padding:10px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;">
                Login
            </button>
        </form>
    </body>
    </html>
    """

@app.post("/auth/login")
async def login_logic(password: str = Form(...)):
    if password == admin_secret_token:
        response = RedirectResponse(url="/admin-ui/admin.html", status_code=303)
        response.set_cookie(key="admin_access_token", value=admin_secret_token, httponly=True)
        return response
    return HTMLResponse("Invalid Token. <a href='/login'>Try again</a>", status_code=401)

# --- 5. Mount Admin & Include Routers ---
# Mount the admin application (Handles UI and Admin API)
mount_admin_app(
    app,
    get_database,
    router_prefix="/admin",
    ui_mount_path="/admin-ui"
)

# Standard App Routers
app.include_router(product_router)
app.include_router(users_router)
app.include_router(subscription_router)
app.include_router(payment_router)
app.include_router(invoice_router)

# --- 6. Root Redirect ---
@app.get("/")
async def root():
    return RedirectResponse(url="/admin-ui/admin.html")