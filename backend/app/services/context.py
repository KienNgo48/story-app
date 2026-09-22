from sqlmodel import Session

from app.models import Node, Story


def full_branch_text(session: Session, node: Node) -> str:
    """Walk parent_id back to the root, then prefix with the story's original text."""
    chain: list[Node] = []
    current: Node | None = node
    while current is not None:
        chain.append(current)
        current = session.get(Node, current.parent_id) if current.parent_id else None
    chain.reverse()

    story = session.get(Story, node.story_id)
    parts = [story.original_text] + [n.content for n in chain if n.content]
    return "\n\n".join(parts)


def last_n_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[-n:])


def assemble_context(session: Session, node: Node) -> dict:
    return {
        "bible": node.bible_snapshot,
        "summary": node.rolling_summary,
        "recent_text": last_n_words(full_branch_text(session, node), 2000),
    }
