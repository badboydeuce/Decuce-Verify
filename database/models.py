"""
Database models for DeuceVerify
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class TransactionType(enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"

class OrderType(enum.Enum):
    ACTIVATION = "activation"
    RENTAL = "rental"

class OrderStatus(enum.Enum):
    PENDING = "pending"
    RECEIVED = "received"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_admin = Column(Boolean, default=False)

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    status = Column(String(50), default="completed")
    reference = Column(String(100), unique=True, nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    order_type = Column(SQLEnum(OrderType), nullable=False)
    service_id = Column(String(50), nullable=False)
    service_name = Column(String(100), nullable=True)
    country_id = Column(String(10), nullable=False)
    country_name = Column(String(100), nullable=True)
    number = Column(String(50), nullable=True)
    request_id = Column(String(50), nullable=True)
    cost = Column(Float, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    otp_code = Column(String(50), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    rental_duration = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    reference = Column(String(100), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    paystack_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
