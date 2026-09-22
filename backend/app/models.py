import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


def utcnow():
    return datetime.now(timezone.utc)


class Story(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str
    title: str
    original_text: str
    bible_json: dict = Field(default_factory=dict, sa_type=JSONB)
    created_at: datetime = Field(default_factory=utcnow)


class Node(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    story_id: uuid.UUID = Field(foreign_key="story.id", index=True)
    parent_id: Optional[uuid.UUID] = Field(default=None, foreign_key="node.id", index=True)
    content: str = ""
    bible_snapshot: dict = Field(default_factory=dict, sa_type=JSONB)
    rolling_summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Option(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    node_id: uuid.UUID = Field(foreign_key="node.id", index=True)
    approach_type: str
    title: str
    pitch: str
    was_chosen: bool = False
