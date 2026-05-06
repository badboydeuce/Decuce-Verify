from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
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
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_admin = Column(Boolean, default=False)

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    status = Column(String(50), default="pending")
    reference = Column(String(100), unique=True)
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    order_type = Column(Enum(OrderType), nullable=False)
    service_id = Column(String(50), nullable=False)
    service_name = Column(String(100))
    country_id = Column(String(10), nullable=False)
    country_name = Column(String(100))
    number = Column(String(50))
    request_id = Column(String(50))  # SMS-Man request_id
    cost = Column(Float, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    otp_code = Column(String(50))
    expires_at = Column(DateTime, nullable=False)
    rental_duration = Column(String(20))  # hour/day/week/month for rentals
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    reference = Column(String(100), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    paystack_data = Column(Text)  # JSON response from Paystack
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
