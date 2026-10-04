"""this file will be for defineing the typed classes for application data"""
from pydantic import BaseModel, Field
from datetime import datetime

class UserBase(BaseModel):
    id: int
    username: str
    email: str
    gpa: int

class Classes(BaseModel): ##most likely be put into a list   
    department: str
    number: int
    name: str
    grade: float
    credit: int
    semester: str
    time: datetime
    weekdays: list ##list of strings such as ["M", "W", "F"]


class Activites(BaseModel):
    isMandatory: bool
    time: datetime
    name: str
    weekdays: list ##list of strings such as ["M", "W", "F"]
    notes: str ## any notes pertaining to the activity 



