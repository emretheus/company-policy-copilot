from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str


class LoginResponse(BaseModel):
    access_token: str
    user_name: str
    role: str
    department: str
    country: str


class DemoUser(BaseModel):
    id: str
    name: str
    role: str
    department: str
    country: str


class AskRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    document_title: str
    is_current_version: bool
    text: str


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    citations: list[CitationOut]
    has_version_conflict: bool
    trace_id: str
