import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from app.db import get_session
from app.models import Story, Node
from app.services.ingest import build_bible

router = APIRouter()


class StoryCreate(BaseModel):
    title: str
    original_text: str


@router.post("/")
def create_story(payload: StoryCreate, session: Session = Depends(get_session)):
    story = Story(user_id="temp-user", title=payload.title, original_text=payload.original_text)
    session.add(story)
    session.commit()
    session.refresh(story)
    return story


@router.get("/{story_id}")
def get_story(story_id: uuid.UUID, session: Session = Depends(get_session)):
    story = session.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.post("/{story_id}/ingest")
async def ingest_story(story_id: uuid.UUID, session: Session = Depends(get_session)):
    """Stage 1 of the AI pipeline: extract the story bible, then create the root
    node (parent_id=None, content="") that branch options/continuations attach to."""
    story = session.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    bible = await build_bible(story.original_text)
    story.bible_json = bible
    session.add(story)

    root = Node(
        story_id=story.id,
        parent_id=None,
        content="",
        bible_snapshot=bible,
        rolling_summary=bible.get("last_scene_summary", ""),
    )
    session.add(root)
    session.commit()
    session.refresh(story)
    session.refresh(root)
    return {"story": story, "root_node_id": root.id}


@router.get("/{story_id}/tree")
def get_tree(story_id: uuid.UUID, session: Session = Depends(get_session)):
    """All nodes for a story, for rendering the branch tree / rewind UI."""
    nodes = session.exec(select(Node).where(Node.story_id == story_id)).all()
    return nodes
