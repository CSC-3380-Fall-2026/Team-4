"""this file will be for calculating finial and projected gpa"""
from fastapi import APIRouter
from tiger_models import Classes

# Initialize the router for this specific module
router = APIRouter()

@router.post('/calculateGPA')
def calculateGPA(classes: Classes)->float: ##takes dictionary of classes, gets 
    pass

@router.post('/getClasses')
def getClasses():
    pass