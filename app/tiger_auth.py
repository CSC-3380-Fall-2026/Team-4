"""this file will be for registering and loging in and out and also managing sessions"""
"""This file will be for check the account permissions and protect any submitted forms"""
import os
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from tiger_models import UserBase, UserAuthSchema
import tiger_gpa as tiger_gpa
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY not found")

router = APIRouter()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
security = HTTPBearer()


@router.post("/login")
async def login(credentials: UserAuthSchema) -> dict[str, str]:
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from None

    if not response or not response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return {
        "access_token": response.session.access_token,
        "token_type": "bearer",
    }

@router.post("/logout")  ##deleted JWT token and returns true for logged ouot
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    try:
        token = credentials.credentials
        supabase.postgrest.auth(token)        
        supabase.auth.sign_out()
        return True
    except Exception:
        return False

@router.post("/signup")
async def signup(credentials: UserAuthSchema) -> dict[str, bool | str]:
    try:
        response = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create the account. Check your details or try another email.",
        ) from None

    if not response or not response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create the account. Please try again.",
        )
    return {
        "created": True,
        "confirmation_required": response.session is None,
    }

@router.get("/validateToken") ##  validates if a token is not expired and is valid
async def validateToken(token:str)->bool:
    try: 
        supabase.auth.get_user(token)
        return True
    except Exception:
        return False


@router.get("/getUser") ##gets all user info
async def getUser(user: UserBase):
    id = user.id
    username = user.username
    classes = user.courses if user.courses else None
    gpa = user.gpa if user.gpa else tiger_gpa.calculateGPA(classes) # type: ignore
    email = user.email
