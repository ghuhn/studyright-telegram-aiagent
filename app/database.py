from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from app.config import settings
import os

# In SQLAlchemy 2.0+, connecting to Postgres requires psycopg2 driver
# But the URL string should just work out of the box if formatted correctly
engine = create_engine(
    settings.database_url
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    active_subject = Column(String, default="General")
    created_at = Column(DateTime, default=datetime.utcnow)

class DocumentMetadata(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # Foreign key conceptually
    filename = Column(String, index=True)
    file_type = Column(String)
    subject = Column(String, default="General", index=True)
    summary = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
