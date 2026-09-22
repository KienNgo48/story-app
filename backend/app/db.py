from sqlmodel import create_engine, Session
from app.config import settings

engine = create_engine(settings.database_url, echo=True)

def get_session():
    with Session(engine) as session:
        yield session