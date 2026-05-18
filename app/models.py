import uuid
from sqlalchemy import Column, Integer, String, Text, Index, Float, Numeric, DateTime, Uuid, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey
from sqlalchemy import Boolean
from sqlalchemy.orm import relationship
from sqlalchemy import text

Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"

    gmail_message_id = Column(String, unique=True, index=True)
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    owner = Column(String)
    date = Column(DateTime)
    merchant = Column(String)
    amount = Column(Numeric)
    card_name = Column(String)
    transaction_type = Column(String)
    raw_email_id = Column(String)
    category = Column(String, nullable=True)        # Needs / Lifestyle / Savings
    subcategory = Column(String, nullable=True)     # Groceries / Restaurant / Utilities
    confidence = Column(Float, nullable=True)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id"))
    


class Oauth_Creds(Base):
    __tablename__ = "oauth_credentials"

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="unique_user_provider"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    

    refresh_token = Column(String, nullable=True)
    access_token = Column(String, nullable=False)
    expiry = Column(DateTime, nullable=True)
    scopes = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id"), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    hashed_password = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    household = relationship("Household", back_populates="users")


class Household(Base):
    __tablename__ = "households"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    users = relationship("User", back_populates="household")

class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    household_id = Column(
        UUID(as_uuid=True),
        ForeignKey("households.id"),
        nullable=False,
        index=True
    )

    raw_text = Column(String, nullable=False, index=True)
    normalized_name = Column(String, nullable=False)

    # optional future use
    default_category = Column(String, nullable=True)

class DebugEmail(Base):
    __tablename__ = "debug_emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    message_id = Column(String, nullable=False, index=True)

    raw_body = Column(Text, nullable=False)

    reason_fail = Column(String, nullable =False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Optional relationship (recommended)
    user = relationship("User", backref="debug_emails")

class RawMessage(Base):
    __tablename__ = "raw_messages"

    __table_args__ = (
        UniqueConstraint("provider", "user_id", "source_message_id", name="uq_raw_provider_user_msgid"),
        Index("ix_raw_household_user_received", "household_id", "user_id", "received_at"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    provider = Column(String, nullable=False, default="gmail")  # gmail for now
    source_message_id = Column(String, nullable=False)          # Gmail message id
    thread_id = Column(String, nullable=True)

    from_email = Column(String, nullable=True)
    to_email = Column(String, nullable=True)
    subject = Column(String, nullable=True)

    received_at = Column(DateTime(timezone=True), nullable=True)
    snippet = Column(Text, nullable=True)

    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)

    headers_json = Column(JSONB, nullable=True)
    raw_json = Column(JSONB, nullable=True)

    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    normalized_message = relationship(
    "NormalizedMessage",
    back_populates="raw_message",
    uselist=False,
    cascade="all, delete-orphan",
    )

class NormalizedMessage(Base):
    __tablename__ = "normalized_messages"

    __table_args__ = (
        UniqueConstraint("raw_message_id", name="uq_normalized_raw_message"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    raw_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.raw_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    normalizer_version = Column(String, nullable=False, default="v1")
    normalized_text = Column(Text, nullable=False)
    normalized_hash = Column(String, nullable=False, index=True)

    meta_json = Column(JSONB, nullable=True)

    normalized_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    raw_message = relationship("RawMessage", back_populates="normalized_message")
    template_match = relationship(
        "TemplateMatch",
        back_populates="normalized_message",
        uselist=False,
        cascade="all, delete-orphan",
    )

    message_type_assignment = relationship(
    "MessageTypeAssignment",
    uselist=False,
    cascade="all, delete-orphan",
    )


class TemplateMatch(Base):
    __tablename__ = "template_matches"

    __table_args__ = (
    UniqueConstraint("normalized_message_id", name="uq_template_matches_normalized_message_id"),
    {"schema": "private"},
)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    normalized_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.normalized_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    template_id = Column(String, nullable=True, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, index=True)  
    # expected values: matched, unknown, ambiguous

    matched_rules_json = Column(JSONB, nullable=True)
    detector_version = Column(String, nullable=False, default="v1")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    normalized_message = relationship("NormalizedMessage", back_populates="template_match")

    __table_args__ = (
        UniqueConstraint("normalized_message_id", name="uq_template_matches_normalized_message_id"),
    )

class DiscoveredMessageType(Base):
    __tablename__ = "discovered_message_types"

    __table_args__ = (
        UniqueConstraint("signature_hash", "sender_key", name="uq_discovered_signature_sender"),
        Index("ix_discovered_sender_examples", "sender_key", "example_count"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    household_id = Column(
        UUID(as_uuid=True),
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider = Column(String, nullable=False, default="gmail", index=True)

    # useful grouping key, usually sender or institution
    sender_key = Column(String, nullable=True, index=True)

    # abstracted text used for similarity
    signature_text = Column(Text, nullable=False)
    signature_hash = Column(String, nullable=False, index=True)

    # first / representative sample
    representative_normalized_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.normalized_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    example_count = Column(Integer, nullable=False, default=1)

    review_status = Column(String, nullable=False, default="new", index=True)
    # new / reviewed / ignored / split_needed

    manually_labeled_template_id = Column(String, nullable=True, index=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assignments = relationship(
        "MessageTypeAssignment",
        back_populates="discovered_message_type",
        cascade="all, delete-orphan",
    )

    representative_normalized_message = relationship("NormalizedMessage")

class MessageTypeAssignment(Base):
    __tablename__ = "message_type_assignments"

    __table_args__ = (
        UniqueConstraint("normalized_message_id", name="uq_message_type_assignment_normalized"),
        Index("ix_assignment_type_score", "discovered_message_type_id", "similarity_score"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    normalized_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.normalized_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    discovered_message_type_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.discovered_message_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    similarity_score = Column(Float, nullable=False)
    assignment_method = Column(String, nullable=False, default="signature_similarity_v1")
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    normalized_message = relationship("NormalizedMessage")
    discovered_message_type = relationship(
        "DiscoveredMessageType",
        back_populates="assignments",
    )