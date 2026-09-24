"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI
from tiger_models import *
import tiger_auth  # Import by using filename. 
app = FastAPI()

app.include_router(tiger_auth.router)

@app.get("/health")
def health():
    return {"healthy"}

