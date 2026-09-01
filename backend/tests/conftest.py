import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.models import User


@pytest.fixture(scope="session")
def db() -> Session:
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def anna_employee(db) -> User:
    return db.query(User).filter_by(email="anna.employee@example.com").first()


@pytest.fixture
def mark_manager(db) -> User:
    return db.query(User).filter_by(email="mark.manager@example.com").first()


@pytest.fixture
def helena_hr(db) -> User:
    return db.query(User).filter_by(email="helena.hr@example.com").first()


@pytest.fixture
def felix_finance(db) -> User:
    return db.query(User).filter_by(email="felix.finance@example.com").first()
