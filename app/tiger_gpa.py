"""this file will be for calculating finial and projected gpa"""
from fastapi import APIRouter, HTTPException
from tiger_models import Classes
import math
from pydantic import BaseModel

router: APIRouter = APIRouter()
# Initialize the router for this specific module
@router.post('/calculateGPA')
def calculateGPA(classes: list[Classes]) -> float:  ##takes dictionary of classes, changed from classes) -> float to current so that it can allow for the process of multiple course
    if not classes:  # This will stop the calculation and return a error response
        raise HTTPException(
            status_code=400,
            detail="Enter at least one course."  # This will explain the problem
        )  # Store the gradepoints for valid grades like A  = 4.3 and other items.
    valid_grades: list[float] = [
        4.3, 4.0, 3.7, 3.5, 3.3, 3.0, 2.8, 2.5, 2.3, 2.0, 1.9, 1.5, 1.3, 1.0, 0.9, 0.5, 0.3, 0.0
    ]
    total_credit_hours: int = 0
    total_quality_points: float = 0.0
    # fresh totals for the calculations
    for course in classes:
        if course.credit <= 0:  # this will reject the courses with a zero or a negative credit hour
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

@router.post("/calculateTotalCredits")
def calculateTotalCredits(classes: list[Classes]) -> int:
    total_credits: int = 0

    for course in classes:
        if course.credit <= 0:
            raise HTTPException(status_code = 400, detail = "course credits have to be greater than zero")

        total_credits += course.credit

    return total_credits

class CumulativeGPARequest(BaseModel):
    currentGPA: float
    completedCredits: int
    classes: list[Classes]

@router.post("/calculateCumulativeGPA")
def calculateCumlativeGPA(data: CumulativeGPARequest) -> float:

        if not math.isfinite(data.currentGPA) or not 0.0 <= data.currentGPA <= 4.3:
            raise HTTPException( status_code=400, detail= "Current GPA has to be between 0.0. and 4.3 to work.")

        if data.completedCredits < 0:
            raise HTTPException( status_code=400, detail= "Completed credits can't be negative.")

        if data.completedCredits == 0 and data.currentGPA != 0.0:
            raise HTTPException( status_code=400, detail= "Your Curret GPA must be 0.0 when no have been completed.")


        semesterGPA: float = calculateGPA(data.classes)
        semesterCredits: int = calculateTotalCredits(data.classes)

        previousPoints: float = data.currentGPA * data.completedCredits
        semesterPoints: float = semesterGPA * semesterCredits

        totalCredits: int  = data.completedCredits + semesterCredits

        cumulativeGPA: float = (previousPoints + semesterPoints) / totalCredits

        return cumulativeGPA

class RequiredGPARequest(BaseModel):
    currentGPA: float
    completedCredits: int
    plannedCredits: int
    targetGPA: float

@router.post("/calculateRequiredGPA")
def calculateRequiredGPA(data: RequiredGPARequest) -> float:

    maxGPA: float = 4.3

    if not math.isfinite(data.currentGPA) or not 0.0 <= data.currentGPA <= maxGPA:
        raise HTTPException( status_code  = 400, detail = "Current GPA has to be between 0.0 and 4.3")

    if not math.isfinite(data.targetGPA) or not 0.0 <= data.targetGPA <= maxGPA:
        raise HTTPException( status_code=400, detail = "The Targer GPA has to be between 0.0 and 4.3.")

    if data.completedCredits < 0:
        raise HTTPException(status_code=400, detail = "completed credits must not be negative.")

    if data.plannedCredits <= 0:
        raise HTTPException( status_code=400, detail = "Planned credits have to be greater than zero.")

    if data.completedCredits == 0 and data.currentGPA != 0.0:
        raise HTTPException(status_code=400, detail = "Current GPA must be 0.0 when no credits have been completed yet.")

    totalCredits: int = data.completedCredits + data.plannedCredits

    requiredGPA: float = (data.targetGPA * totalCredits - data.currentGPA * data.completedCredits) / data.plannedCredits

    if requiredGPA > maxGPA + 1e-9:

        maxCumulativeGPA: float = (data.currentGPA * data.completedCredits + maxGPA * data.plannedCredits) / totalCredits

        raise HTTPException(status_code=400, detail = (f"Target GPA is unreachable." f"The Highest possible of a cumulative GPA is " f"{maxCumulativeGPA:.2f}"))

    return min(maxGPA, max(0.0, requiredGPA))
