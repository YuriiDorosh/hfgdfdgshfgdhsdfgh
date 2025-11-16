from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.db import Base


class ProxyLog(Base):
    __tablename__ = "proxy_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    client_ip = Column(String(45), nullable=True)
    method = Column(String(10), nullable=False)
    path = Column(Text, nullable=False)
    upstream_url = Column(Text, nullable=False)
    query_params = Column(JSONB, nullable=True)
    request_headers = Column(JSONB, nullable=True)
    request_body = Column(Text, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_headers = Column(JSONB, nullable=True)
    response_body = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
