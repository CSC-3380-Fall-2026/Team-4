"""this file will be for defineing the typed classes for application data"""
from pydantic import BaseModel, Field

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


