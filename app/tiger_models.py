"""this file will be for defineing the typed classes for application data"""
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

class UserBase(BaseModel):
    id: str
    username: str | None = None
    email: str
    gpa: float | None = None
    courses: list = []

class Classes(BaseModel): ##most likely be put into a list   
    department: str
    number: int
    name: str
    grade: float
    credit: int
    semester: str
    time: datetime
    weekdays: list ##list of strings such as ["M", "W", "F"]
    category: str ### core, tech elective or other

class Activites(BaseModel):
    isMandatory: bool
    time: datetime
    name: str
    weekdays: list ##list of strings such as ["M", "W", "F"]
    notes: str ## any notes pertaining to the activity 

class UserAuthSchema(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    username: str | None = None
    gpa: float | None = Field(default=None, ge=0, le=4.3)
    courses: list = []

class Meeting(BaseModel):
    days: list[str]  ##such as ["M", "W", "F"]
    start: str  ## "HH:MM", 24 hour
    end: str
    location: str = ""

class ScheduleSection(BaseModel):
    department: str
    number: int
    name: str
    section: str
    credit: int = 0
    meetings: list[Meeting] = []

class Commitment(BaseModel):
    name: str
    days: list[str]
    start: str
    end: str
    notes: str = ""

class ScheduleIn(BaseModel):
    name: str = Field(min_length=1)
    semester: str
    sections: list[ScheduleSection] = []
    commitments: list[Commitment] = []

class ScheduleOut(ScheduleIn):
    id: str
    created_at: str | None = None
    updated_at: str | None = None
