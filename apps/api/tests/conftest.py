import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Base
from app.settings import Settings


@pytest.fixture
def client(tmp_path):
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", storage_dir=tmp_path / "storage")
    )
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        yield client
