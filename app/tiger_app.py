"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from tiger_models import *
import tiger_auth  # Import by using filename.
import tiger_gpa
import tiger_scheduler

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_scheduler.router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.get("/health")
def health():
    return {"healthy"}

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "templates" / "tiger_home.html")

@app.get("/signin")
def signin_page():
    return FileResponse(BASE_DIR / "templates" / "tiger_signin.html")

@app.get("/profile-page")
def profile_page():
    return FileResponse(BASE_DIR / "templates" / "tiger_profile.html")

@app.get("/schedule-page")
def schedule_page():
    return FileResponse(BASE_DIR / "templates" / "tiger_schedule.html")
