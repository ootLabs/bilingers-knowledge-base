"""SQLAlchemy models.

Importing this package registers every table on `Base.metadata`. Alembic's
`env.py` and any code reading the metadata depend on that, so a new model
module belongs in the imports below or it is invisible to migrations.
"""

from app.models.audit import AuditAction, PanelAuditEvent
from app.models.base import PERSONAL_DATA, Base, TimestampMixin, personal_data_columns
from app.models.chat import ChatSession, Query
from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.knowledge import KnowledgeBaseVersion, KnowledgeGap, KnowledgeGapStatus
from app.models.panel import (
    PanelLoginAttempt,
    PanelPasswordReset,
    PanelRole,
    PanelSession,
    PanelUser,
)
from app.models.two_factor import PanelBackupCode, PanelTotpSecret
from app.models.user import User

__all__ = [
    "PERSONAL_DATA",
    "AuditAction",
    "Base",
    "ChatSession",
    "Document",
    "DocumentStatus",
    "DocumentVersion",
    "KnowledgeBaseVersion",
    "KnowledgeGap",
    "KnowledgeGapStatus",
    "PanelAuditEvent",
    "PanelBackupCode",
    "PanelLoginAttempt",
    "PanelPasswordReset",
    "PanelRole",
    "PanelSession",
    "PanelTotpSecret",
    "PanelUser",
    "Query",
    "TimestampMixin",
    "User",
    "personal_data_columns",
]
