import os
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base, get_db
from api.routers.alerts import router


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    # SQLite only autoincrements INTEGER; PostgreSQL uses BIGSERIAL in production.
    @event.listens_for(Session, "before_flush")
    def assign_test_ids(session, *_):
        from api.models.models import Alert, Prediction, ProjectUpdate
        for model, key in ((Alert, "alert_id"), (Prediction, "prediction_id"), (ProjectUpdate, "id")):
            existing = [getattr(r, key) for r in session.query(model).all()]
            pending = [getattr(r, key) for r in session.new if isinstance(r, model) and getattr(r, key) is not None]
            next_id = max(existing + pending + [0]) + 1
            for row in session.new:
                if isinstance(row, model) and getattr(row, key) is None:
                    setattr(row, key, next_id)
                    next_id += 1
    with Session(engine, autoflush=False) as session:
        yield session
    event.remove(Session, "before_flush", assign_test_ids)
    engine.dispose()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
