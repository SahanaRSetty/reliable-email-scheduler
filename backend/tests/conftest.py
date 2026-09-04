from uuid import uuid4
import pytest
from app.models.sender import EmailSender
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.services.encryption import encrypt_smtp_password


def get_test_database_url() -> str:
    return settings.database_url.rsplit("/", 1)[0] + "/email_scheduler_test"


TEST_DATABASE_URL = get_test_database_url()

engine = create_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=engine)

    yield

    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_user_and_sender(db):
    unique_id = uuid4().hex

    user = User(
        google_id=f"pytest-user-{unique_id}",
        name="Pytest User",
        email=f"pytest-{unique_id}@example.com",
    )

    db.add(user)
    db.flush()

    sender = EmailSender(
        user_id=user.id,
        email=f"test-sender-{unique_id}@example.com",
        display_name="Pytest Sender",
        smtp_host="smtp.test.local",
        smtp_port=587,
        smtp_username="test@example.com",
        smtp_password=encrypt_smtp_password("test-password"),
    )

    db.add(sender)
    db.commit()

    db.refresh(user)
    db.refresh(sender)

    return user, sender

@pytest.fixture
def db():
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    def override_get_db():
        db = TestingSessionLocal()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()