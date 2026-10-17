"""this file will be for defineing the typed classes for application data"""
from pydantic import BaseModel, Field, EmailStr

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

class UserAuthSchema(BaseModel):
    email: EmailStr
    password: str

