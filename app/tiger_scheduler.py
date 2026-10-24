""" 
Build API routes and database functions that let signed-in students create, save, reopen, edit, and delete schedules.
Store the schedule name, semester, and selected class sections in Supabase. 
Determine ownership from the signed-in account and prevent students from accessing or modifying another student's schedules
"""
from fastapi import APIRouter
from tiger_models import 

# Initialize the router for this specific module
router = APIRouter()

@router.post("/create-schedule")
def create_schedule():

    pass

@router.post("/update-schedule")
def update_schedule():
    pass

@router.get("/get-schedule")
def get_schedule():
    pass

@router.delete('/delete-schedule')
def delete_schedule():
    pass