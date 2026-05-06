# Database models
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import enum

Base = declarative_base()

class TransactionType(enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"

class TransactionStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class OrderStatus(enum.Enum):
    ACTIVE = "active"
    RECEIVED = "received"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    balance = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    total_orders = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    request_id = Column(Integer)
    service_id = Column(Integer, nullable=False)
    service_name = Column(String(100))
    country_id = Column(Integer, nullable=False)
    country_name = Column(String(100))
    number = Column(String(50))
    cost = Column(Float, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.ACTIVE)
    otp_code = Column(String(20))
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    payment_method = Column(String(50))
    payment_reference = Column(String(200), unique=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class PriceCache(Base):
    __tablename__ = "price_cache"
    
    id = Column(Integer, primary_key=True)
    country_id = Column(Integer)
    service_id = Column(Integer)
    cost = Column(Float)
    available_count = Column(Integer)
    last_updated = Column(DateTime, default=datetime.utcnow)

class DatabaseManager:
    def __init__(self, database_url):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
    def create_tables(self):
        Base.metadata.create_all(self.engine)
        
    def get_session(self):
        return self.Session()
