"""this file will be for calculating finial and projected gpa"""
from fastapi import APIRouter, HTTPException
from tiger_models import Classes 

# Initialize the router for this specific module
router = APIRouter()

@router.post('/calculateGPA')
def calculateGPA(classes: list[Classes])->float: ##takes dictionary of classes, changed from classes) -> float to current so that it can allow for the process of multiple course
    if not classes: # This will stop the calculation and return a error response 
        raise HTTPException(
            status_code=400,
            detail="Enter a minimum of one course." # This will explain the problem 
        )
total_credit_hours = 0
total_quality_hours = 0.0
        
for course in classes:
     pass 
@router.post('/getClasses')
def getClasses():
    pass
