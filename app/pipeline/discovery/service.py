from sqlalchemy.orm import Session, joinedload

from app.models import NormalizedMessage, RawMessage
from app.models import DiscoveredMessageType, MessageTypeAssignment
from app.pipeline.discovery.signature import (
    build_signature_text,
    build_signature_hash,
    build_sender_key,
)
from app.pipeline.discovery.similarity import similarity_ratio


ASSIGNMENT_METHOD = "signature_similarity_v1"


def get_unassigned_normalized_messages(db: Session, limit: int | None = None):
    query = (
        db.query(NormalizedMessage)
        .join(RawMessage, RawMessage.id == NormalizedMessage.raw_message_id)
        .outerjoin(
            MessageTypeAssignment,
            MessageTypeAssignment.normalized_message_id == NormalizedMessage.id,
        )
        .filter(MessageTypeAssignment.id.is_(None))
        .options(joinedload(NormalizedMessage.raw_message))
        .order_by(NormalizedMessage.normalized_at.asc())
    )

    if limit is not None:
        query = query.limit(limit)

    return query.all()


def get_candidate_types_for_sender(
    db: Session,
    household_id,
    user_id,
    provider: str,
    sender_key: str,
):
    """
    return (
        db.query(DiscoveredMessageType)
        .filter(DiscoveredMessageType.household_id == household_id)
        .filter(DiscoveredMessageType.user_id == user_id)
        .filter(DiscoveredMessageType.provider == provider)
        .filter(DiscoveredMessageType.sender_key == sender_key)
        .all()
    )"""
    return (
        db.query(DiscoveredMessageType)
        .filter(DiscoveredMessageType.household_id == household_id)
        .filter(DiscoveredMessageType.provider == provider)
        .filter(DiscoveredMessageType.sender_key == sender_key)
        .all()
    )


def assign_message_to_type(
    db: Session,
    normalized_message: NormalizedMessage,
    similarity_threshold: float = 0.92,
    maybe_threshold: float = 0.80,
):
    raw = normalized_message.raw_message

    provider = raw.provider or "gmail"
    sender_key = build_sender_key(raw.from_email, raw.subject)
    signature_text = build_signature_text(normalized_message.normalized_text)
    signature_hash = build_signature_hash(signature_text)

    # Exact signature hash fast path
    exact = (
        db.query(DiscoveredMessageType)
        .filter(DiscoveredMessageType.household_id == raw.household_id)
        .filter(DiscoveredMessageType.user_id == raw.user_id)
        .filter(DiscoveredMessageType.provider == provider)
        .filter(DiscoveredMessageType.sender_key == sender_key)
        .filter(DiscoveredMessageType.signature_hash == signature_hash)
        .first()
    )

    if exact:
        assignment = MessageTypeAssignment(
            normalized_message_id=normalized_message.id,
            discovered_message_type_id=exact.id,
            similarity_score=1.0,
            assignment_method=ASSIGNMENT_METHOD,
        )
        db.add(assignment)
        exact.example_count += 1

        return {
            "action": "assigned_exact",
            "discovered_message_type_id": str(exact.id),
            "score": 1.0,
            "sender_key": sender_key,
        }

    candidates = get_candidate_types_for_sender(
        db=db,
        household_id=raw.household_id,
        user_id=raw.user_id,
        provider=provider,
        sender_key=sender_key,
    )

    best_type = None
    best_score = 0.0

    for candidate in candidates:
        score = similarity_ratio(signature_text, candidate.signature_text)
        if score > best_score:
            best_score = score
            best_type = candidate

    if best_type and best_score >= similarity_threshold:
        assignment = MessageTypeAssignment(
            normalized_message_id=normalized_message.id,
            discovered_message_type_id=best_type.id,
            similarity_score=best_score,
            assignment_method=ASSIGNMENT_METHOD,
        )
        db.add(assignment)
        best_type.example_count += 1

        return {
            "action": "assigned_similar",
            "discovered_message_type_id": str(best_type.id),
            "score": round(best_score, 4),
            "sender_key": sender_key,
        }

    # create new discovered type
    new_type = DiscoveredMessageType(
        household_id=raw.household_id,
        user_id=raw.user_id,
        provider=provider,
        sender_key=sender_key,
        signature_text=signature_text,
        signature_hash=signature_hash,
        representative_normalized_message_id=normalized_message.id,
        example_count=1,
        review_status="new" if best_score < maybe_threshold else "reviewed",
        manually_labeled_template_id=None,
    )
    db.add(new_type)
    db.flush()  # get new_type.id

    assignment = MessageTypeAssignment(
        normalized_message_id=normalized_message.id,
        discovered_message_type_id=new_type.id,
        similarity_score=1.0,
        assignment_method=ASSIGNMENT_METHOD,
    )
    db.add(assignment)

    return {
        "action": "created_new_type",
        "discovered_message_type_id": str(new_type.id),
        "score": 1.0,
        "best_existing_score": round(best_score, 4),
        "sender_key": sender_key,
    }


def cluster_unassigned_messages(
    db: Session,
    limit: int | None = None,
    similarity_threshold: float = 0.92,
    maybe_threshold: float = 0.80,
):
    messages = get_unassigned_normalized_messages(db, limit=limit)

    processed = 0
    assigned_exact = 0
    assigned_similar = 0
    created_new_type = 0

    details = []

    for msg in messages:
        result = assign_message_to_type(
            db=db,
            normalized_message=msg,
            similarity_threshold=similarity_threshold,
            maybe_threshold=maybe_threshold,
        )

        processed += 1

        action = result["action"]
        if action == "assigned_exact":
            assigned_exact += 1
        elif action == "assigned_similar":
            assigned_similar += 1
        elif action == "created_new_type":
            created_new_type += 1

        details.append({
            "normalized_message_id": str(msg.id),
            **result,
        })

    db.commit()

    return {
        "processed": processed,
        "assigned_exact": assigned_exact,
        "assigned_similar": assigned_similar,
        "created_new_type": created_new_type,
        "details": details,
    }