"""this file will be for defineing the typed classes for application data"""
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

class UserBase(BaseModel):
    id: int
    username: str
    email: str
    gpa: int
    courses: list

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

class Activites(BaseModel):
    isMandatory: bool
    time: datetime
    name: str
    weekdays: list ##list of strings such as ["M", "W", "F"]
    notes: str ## any notes pertaining to the activity 