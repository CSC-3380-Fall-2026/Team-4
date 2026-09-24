"""this file will be for registering and loging in and out and also managing sessions"""
"""This file will be for check the account permissions and protect any submitted forms"""
from fastapi import APIRouter
from tiger_models import *

router = APIRouter()

@router.post("/login") ##login using supabase and returns a JWT token and return true/false for login successful
async def login()->tuple[str, bool]:
    pass

@router.post("/logout")##deleted JWT token and returns true for logged ouot
async def logout()->bool:
    pass

@router.post("/signup")##creates an account using supabase
async def signup()->tuple[str, bool]:
    pass

@router.get("/validateToken") ##  validates if a token is not expired and is valid
async def validateToken(token:str)->bool:
    pass

@router.get("/getUser") ##gets all user info
async def getUser()->UserBase:
    pass

