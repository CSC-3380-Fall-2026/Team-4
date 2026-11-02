"""this file will be for registering and loging in and out and also managing sessions"""
"""This file will be for check the account permissions and protect any submitted forms"""
from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from tiger_models import UserBase, UserAuthSchema
import tiger_gpa
from supabase import Client
from tiger_db import get_database


router = APIRouter()
supabase: Client = get_database()
security = HTTPBearer()


@router.post("/login") ##login using supabase and returns a JWT token and return true/false for login successful
async def login(credentials: UserAuthSchema)->tuple[str, bool]:
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        
        if response and response.session:
            return response.session.access_token, True
        
        return "Auth succeeded", False
        
    except Exception as e:
        return f"Auth failed: {str(e)}", False

@router.post("/logout")  ##deleted JWT token and returns true for logged ouot
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    try:
        token = credentials.credentials
        supabase.postgrest.auth(token)        
        supabase.auth.sign_out()
        return True
    except Exception:
        return False

@router.post("/signup")##creates an account using supabase
async def signup(credentials: UserAuthSchema)->tuple[str, bool]:
    try:
        response = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })

        if response and response.user:
            return f"User ID: {response.user.id}", True
        
        return "Registration initiated", False
    
    except Exception as e:
        return f"Signup failed: {str(e)}", False

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

