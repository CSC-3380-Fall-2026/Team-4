"""this file will be for calculating finial and projected gpa"""
from fastapi import APIRouter, HTTPException
import math
from tiger_models import Classes, CumulativeGPARequest, RequiredGPARequest

router: APIRouter = APIRouter()
# Initialize the router for this specific module

MAX_GPA: float = 4.3
# LSU plus/minus scale: A/B/C/D are 4/3/2/1, plus or minus adds or takes 0.3, F is 0.0
VALID_GRADES: set[float] = {0.0} | {round(base + step, 1) for base in (1, 2, 3, 4) for step in (-0.3, 0, 0.3)}


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def validate_gpa(gpa: float, label: str) -> None:
    # rejects NaN, infinity and anything outside the 0.0 - MAX_GPA scale
    if not math.isfinite(gpa) or not 0.0 <= gpa <= MAX_GPA:
        raise bad_request(f"{label} has to be between 0.0 and {MAX_GPA}.")


def validate_history(currentGPA: float, completedCredits: int) -> None:
    validate_gpa(currentGPA, "Current GPA")
    if completedCredits < 0:
        raise bad_request("Completed credits can't be negative.")
    if completedCredits == 0 and currentGPA != 0.0:
        raise bad_request("Current GPA must be 0.0 when no credits have been completed yet.")


@router.post('/calculateGPA')
def calculateGPA(classes: list[Classes]) -> float:  ##takes dictionary of classes, changed from classes) -> float to current so that it can allow for the process of multiple course
    if not classes:  # This will stop the calculation and return a error response
        raise bad_request("Enter at least one course.")
    # this also rejects the courses with a zero or a negative credit hour
    total_credit_hours: int = calculateTotalCredits(classes)
    total_quality_points: float = 0.0
    for course in classes:
        if course.grade not in VALID_GRADES:
            #this will reject grades that are not in the accepted grade point list.
            raise bad_request("Enter only valid grade points like 4.0 for an A 3.0 for a B ....")
        # this will multiply the credits by grade points
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
            raise bad_request("Course credits have to be greater than zero.")

        total_credits += course.credit

    return total_credits


@router.post("/calculateCumulativeGPA")
def calculateCumlativeGPA(data: CumulativeGPARequest) -> float:
    validate_history(data.currentGPA, data.completedCredits)

    semesterGPA: float = calculateGPA(data.classes)
    semesterCredits: int = calculateTotalCredits(data.classes)

    previousPoints: float = data.currentGPA * data.completedCredits
    semesterPoints: float = semesterGPA * semesterCredits

    totalCredits: int = data.completedCredits + semesterCredits
    cumulativeGPA: float = (previousPoints + semesterPoints) / totalCredits
    return cumulativeGPA


@router.post("/calculateRequiredGPA")
def calculateRequiredGPA(data: RequiredGPARequest) -> float:
    validate_history(data.currentGPA, data.completedCredits)
    validate_gpa(data.targetGPA, "Target GPA")
    if data.plannedCredits <= 0:
        raise bad_request("Planned credits have to be greater than zero.")

    previousPoints: float = data.currentGPA * data.completedCredits
    totalCredits: int = data.completedCredits + data.plannedCredits
    requiredGPA: float = (data.targetGPA * totalCredits - previousPoints) / data.plannedCredits

    if requiredGPA > MAX_GPA + 1e-9:
        maxCumulativeGPA: float = (previousPoints + MAX_GPA * data.plannedCredits) / totalCredits
        raise bad_request(
            f"Target GPA is unreachable. "
            f"The highest possible cumulative GPA is {maxCumulativeGPA:.2f}."
        )

    return min(MAX_GPA, max(0.0, requiredGPA))
