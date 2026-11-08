import pytest

from bi_analyst.config import Settings
from bi_analyst.db import Database
from bi_analyst.demo_data import create_demo_db


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    path = create_demo_db(str(tmp_path_factory.mktemp("db") / "demo.db"))
    return f"sqlite:///{path}"


@pytest.fixture()
def settings(demo_db, tmp_path):
    return Settings(db_url=demo_db, trace_dir=str(tmp_path / "traces"))


@pytest.fixture()
def db(settings):
    return Database(settings.db_url)
