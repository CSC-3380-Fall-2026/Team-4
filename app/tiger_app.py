"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from tiger_models import *
import tiger_catalog
import tiger_auth  # Import by using filename. 
import tiger_gpa

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_catalog.router)

@app.get("/health")
def health():
    return {"healthy"}

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request, "tiger_home.html", {"name": "willyt"})

