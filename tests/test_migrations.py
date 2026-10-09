"""The Alembic migrations must build exactly the schema the models describe."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade

from runnify import create_app
from runnify.config import TestConfig
from runnify.extensions import db


def test_migrations_match_models(tmp_path):
    class MigratedConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"

    app = create_app(MigratedConfig)
    with app.app_context():
        upgrade()
        with db.engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), db.metadata)
        db.engine.dispose()
    assert diff == [], f"models and migrations differ; run `flask db migrate`: {diff}"
