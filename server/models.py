from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True)
    api_key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class Log(Base):
    __tablename__ = "logs"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, index=True)
    phone = Column(String, index=True)
    token = Column(String, index=True)
    otp = Column(String)
    template_snapshot = Column(String) # Record the actual message sent
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, unique=True, nullable=False)
    language = Column(String, default="es_mx") # e.g., es_mx, en_us
    category = Column(String, default="otp")   # e.g., otp, promo
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String, default="ai_generated") # ai_generated, manual
