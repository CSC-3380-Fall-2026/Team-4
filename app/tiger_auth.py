"""this file will be for registering and loging in and out and also managing sessions"""
"""This file will be for check the account permissions and protect any submitted forms"""
import os
import requests
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from tiger_models import UserBase, UserAuthSchema, ProfileUpdate
from dotenv import load_dotenv
from pathlib import Path
from supabase import create_client, Client

load_dotenv(Path(__file__).resolve().parent / ".env")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY not found")

router = APIRouter()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
security = HTTPBearer()


def user_client(token: str) -> Client:
    """A client that acts as the signed-in student, so the database ownership policies apply."""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client.postgrest.auth(token)
    return client


class Session:
    def __init__(self, user_id: str, email: str, token: str):
        self.user_id = user_id
        self.email = email
        self.token = token
        self.db = user_client(token)


def current_session(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Session:
    """Dependency for protected routes: identifies the student from the bearer token."""
    token = credentials.credentials
    try:
        result = supabase.auth.get_user(token)
        user = result.user if result else None
    except Exception:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return Session(user.id, user.email or "", token)


@router.post("/signup")  ##creates an account using supabase
async def signup(credentials: UserAuthSchema) -> dict:
    try:
        response = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Signup failed: {e}")
    if not response or not response.user:
        raise HTTPException(status_code=400, detail="Signup failed")
    token = response.session.access_token if response.session else None
    return {"user_id": response.user.id, "access_token": token}


@router.post("/login")  ##login using supabase and returns a JWT token
async def login(credentials: UserAuthSchema) -> dict:
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not response or not response.session:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": response.session.access_token, "user_id": response.user.id}


@router.post("/logout")  ##revokes the session so the token stops working
async def logout(session: Session = Depends(current_session)) -> dict:
    requests.post(
        f"{SUPABASE_URL}/auth/v1/logout",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {session.token}"},
        timeout=10,
    )
    return {"logged_out": True}


@router.get("/validateToken")  ##  validates if a token is not expired and is valid
async def validateToken(token: str) -> bool:
    try:
        supabase.auth.get_user(token)
        return True
    except Exception:
        return False


@router.get("/getUser")  ##gets all user info
async def getUser(session: Session = Depends(current_session)) -> UserBase:
    return _load_profile(session)


@router.get("/profile")
async def get_profile(session: Session = Depends(current_session)) -> UserBase:
    return _load_profile(session)


@router.put("/profile")
async def update_profile(update: ProfileUpdate, session: Session = Depends(current_session)) -> UserBase:
    row = {
        "id": session.user_id,
        "email": session.email,
        "username": update.username,
        "gpa": update.gpa,
        "courses": update.courses,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.db.table("profiles").upsert(row).execute()
    return _load_profile(session)


def _load_profile(session: Session) -> UserBase:
    rows = session.db.table("profiles").select("*").eq("id", session.user_id).execute().data
    row = rows[0] if rows else {}
    return UserBase(
        id=session.user_id,
        username=row.get("username"),
        email=row.get("email") or session.email,
        gpa=float(row["gpa"]) if row.get("gpa") is not None else None,
        courses=row.get("courses") or [],
    )
