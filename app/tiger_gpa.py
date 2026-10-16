"""this file will be for calculating finial and projected gpa"""
from fastapi import APIRouter, HTTPException
from tiger_models import Classes 

router: APIRouter = APIRouter()
# Initialize the router for this specific module

@router.post('/calculateGPA')
def calculateGPA(classes: list[Classes])->float: ##takes dictionary of classes, changed from classes) -> float to current so that it can allow for the process of multiple course
    if not classes: # This will stop the calculation and return a error response 
        raise HTTPException(
            status_code=400,
            detail="Enter at least one course." # This will explain the problem 
        ) # Store the gradepoints for valid grades like A  = 4.3 and other items.
    valid_grades: list[float] = [ 
          4.3 , 4.0 , 3.7 , 3.5,  3.3 , 3.0 , 2.8 , 2.5 , 2.3 , 2.0 , 1.9, 1.5 , 1.3 , 1.0 , 0.9 , 0.5 , 0.3, 0.0 ]
        
    total_credit_hours: int = 0
    total_quality_points:  float = 0.0
        # fresh totals for the calculations
    for course in classes:
        if course.credit <= 0: # this will reject the courses with a zero or a negative credit hour
           raise HTTPException(
              status_code=400,
              detail="The amount of course credits must be greater than 0, "
        )
    if course.grade not in valid_grades:
        raise HTTPException(
           status_code=400,
           #this will reject grades that are not in the accepted grade point list.
           detail=" Enter only valid grade points like 4.0 for an A 3.0 for a B ...."
       )

    # this will multiply the credits by grade points and add the course credit
    total_credit_hours += course.credit
    total_quality_points += course.grade * course.credit

# this will divide the quality points by the credits
    return total_quality_points / total_credit_hours

            # this will return an error if the course has not been implemented yet when its trying to retrieve it.
@router.post('/getClasses')
def getClasses() -> list[Classes]:
    raise HTTPException(
        status_code=501,
        detail="Could not retreieve saved course, Has not been created yet."
    )

