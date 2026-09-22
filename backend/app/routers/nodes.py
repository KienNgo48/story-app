import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from app.db import get_session
from app.models import Node, Option
from app.services.ai_client import call_model, parse_json
from app.services.context import assemble_context, full_branch_text
from app.prompts import (
    BRANCH_OPTIONS_SYSTEM,
    BRANCH_OPTIONS_USER,
    CONTINUATION_SYSTEM,
    CONTINUATION_USER,
    BIBLE_UPDATE_SYSTEM,
    BIBLE_UPDATE_USER,
    SUMMARY_UPDATE_SYSTEM,
    SUMMARY_UPDATE_USER,
)

router = APIRouter()

N_OPTIONS = 3
TARGET_LENGTH = "400-600 words"
MAX_SUMMARY_WORDS = 300


@router.post("/{node_id}/options")
async def get_options(node_id: uuid.UUID, session: Session = Depends(get_session)):
    """Stage 3: assemble context, propose N distinct branch options, persist and return them."""
    node = session.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    ctx = assemble_context(session, node)
    user = BRANCH_OPTIONS_USER.format(
        bible_json=json.dumps(ctx["bible"]),
        rolling_summary=ctx["summary"],
        verbatim_recent_text=ctx["recent_text"],
        n=N_OPTIONS,
    )
    raw = await call_model(BRANCH_OPTIONS_SYSTEM, user, json_mode=True)
    data = parse_json(raw)

    options = [
        Option(
            node_id=node.id,
            approach_type=opt["approach_type"],
            title=opt["title"],
            pitch=opt["pitch"],
        )
        for opt in data["options"]
    ]
    session.add_all(options)
    session.commit()
    for o in options:
        session.refresh(o)
    return options


class ContinueBody(BaseModel):
    option_id: uuid.UUID


@router.post("/{node_id}/continue")
async def continue_node(node_id: uuid.UUID, body: ContinueBody, session: Session = Depends(get_session)):
    """Stage 4 + 5: write the chosen continuation, then update the bible and rolling
    summary onto a new child node so each branch keeps its own consistent state."""
    node = session.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    option = session.get(Option, body.option_id)
    if not option or option.node_id != node.id:
        raise HTTPException(status_code=404, detail="Option not found for this node")

    ctx = assemble_context(session, node)
    bible = ctx["bible"]

    system = CONTINUATION_SYSTEM.format(
        voice_notes=bible.get("voice_notes", ""),
        established_facts="\n".join(f"- {f}" for f in bible.get("established_facts", [])),
    )
    user = CONTINUATION_USER.format(
        bible_json=json.dumps(bible),
        rolling_summary=ctx["summary"],
        verbatim_recent_text=ctx["recent_text"],
        title=option.title,
        pitch=option.pitch,
        target_length=TARGET_LENGTH,
        pov=bible.get("pov", "third limited, past tense"),
    )
    passage = await call_model(system, user, max_tokens=1500)

    option.was_chosen = True
    session.add(option)

    new_bible = parse_json(await call_model(
        BIBLE_UPDATE_SYSTEM,
        BIBLE_UPDATE_USER.format(existing_bible_json=json.dumps(bible), newly_generated_text=passage),
        json_mode=True,
    ))
    new_summary = await call_model(
        SUMMARY_UPDATE_SYSTEM.format(max_words=MAX_SUMMARY_WORDS),
        SUMMARY_UPDATE_USER.format(existing_summary=ctx["summary"], newly_generated_text=passage),
    )

    child = Node(
        story_id=node.story_id,
        parent_id=node.id,
        content=passage,
        bible_snapshot=new_bible,
        rolling_summary=new_summary.strip(),
    )
    session.add(child)
    session.commit()
    session.refresh(child)
    return child


@router.get("/{node_id}/path")
def get_path(node_id: uuid.UUID, session: Session = Depends(get_session)):
    """Full branch text: original story + every node's content from root to here."""
    node = session.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"text": full_branch_text(session, node)}
