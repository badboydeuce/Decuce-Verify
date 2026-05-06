"""
Database models for DeuceVerify
SQLAlchemy ORM models for users, orders, transactions, and price cache
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, Enum as SQLEnum, BigInteger, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from datetime import datetime
import enum
import os
from loguru import logger

# Create declarative base
Base = declarative_base()

# ==================== ENUMS ====================

class TransactionType(enum.Enum):
    """Transaction type enum"""
    CREDIT = "credit"      # Money added to wallet
    DEBIT = "debit"        # Money deducted from wallet

class TransactionStatus(enum.Enum):
    """Transaction status enum"""
    PENDING = "pending"      # Transaction initiated, waiting for confirmation
    COMPLETED = "completed"  # Transaction completed successfully
    FAILED = "failed"        # Transaction failed
    REFUNDED = "refunded"    # Transaction was refunded

class OrderStatus(enum.Enum):
    """Order status enum"""
    PENDING = "pending"      # Order created, waiting for number
    ACTIVE = "active"        # Number rented, waiting for OTP
    RECEIVED = "received"    # OTP received
    EXPIRED = "expired"      # Number expired without OTP
    CANCELLED = "cancelled"  # User cancelled
    REFUNDED = "refunded"    # Refunded

class PaymentMethod(enum.Enum):
    """Payment method enum"""
    PAYSTACK = "paystack"
    CRYPTO = "crypto"
    TELEGRAM_WALLET = "telegram_wallet"
    ADMIN_MANUAL = "admin_manual"
    REFUND = "refund"

# ==================== USER MODEL ====================

class User(Base):
    """User model for storing Telegram users"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    
    # Wallet
    balance = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    total_orders = Column(Integer, default=0)
    total_refunds = Column(Integer, default=0)
    
    # Status
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    
    # Referral system
    referral_code = Column(String(50), unique=True, nullable=True)
    referred_by = Column(BigInteger, nullable=True)
    referral_earnings = Column(Float, default=0.0)
    referral_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Metadata
    language_code = Column(String(10), default="en")
    notification_enabled = Column(Boolean, default=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_user_telegram_id', 'telegram_id'),
        Index('idx_user_username', 'username'),
        Index('idx_user_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username}, balance={self.balance})>"


# ==================== ORDER MODEL ====================

class Order(Base):
    """Order model for number rentals"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    
    # SMS-Man details
    request_id = Column(Integer, nullable=True)  # SMS-Man request ID
    service_id = Column(Integer, nullable=False)
    service_name = Column(String(100), nullable=False)
    country_id = Column(Integer, nullable=False)
    country_name = Column(String(100), nullable=False)
    number = Column(String(50), nullable=True)
    
    # Pricing (with profit markup)
    cost = Column(Float, nullable=False)  # What customer paid (marked up)
    original_cost = Column(Float, default=0.0)  # What we paid SMS-Man
    profit = Column(Float, default=0.0)  # Profit = cost - original_cost
    profit_percent = Column(Float, default=0.0)  # (profit/original_cost)*100
    
    # Status
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    
    # OTP/SMS data
    otp_code = Column(String(20), nullable=True)
    sms_text = Column(Text, nullable=True)
    sms_received_at = Column(DateTime, nullable=True)
    
    # Timing
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    
    # Refund
    refund_amount = Column(Float, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    refund_reason = Column(String(200), nullable=True)
    
    # Metadata
    retry_count = Column(Integer, default=0)
    last_checked = Column(DateTime, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_order_user_id', 'user_id'),
        Index('idx_order_status', 'status'),
        Index('idx_order_created_at', 'created_at'),
        Index('idx_order_request_id', 'request_id'),
        Index('idx_order_user_status', 'user_id', 'status'),
    )
    
    def __repr__(self):
        return f"<Order(id={self.id}, user_id={self.user_id}, service={self.service_name}, cost={self.cost})>"


# ==================== TRANSACTION MODEL ====================

class Transaction(Base):
    """Transaction model for wallet history"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    
    # Amounts
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    
    # Type and status
    type = Column(SQLEnum(TransactionType), nullable=False)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    
    # Payment details
    payment_method = Column(String(50), nullable=True)
    payment_reference = Column(String(200), unique=True, nullable=True)
    
    # Related order (for debit/refund transactions)
    order_id = Column(Integer, nullable=True, index=True)
    
    # Description and metadata
    description = Column(Text, nullable=True)
    metadata = Column(Text, nullable=True)  # JSON string for additional data
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Admin notes (for manual adjustments)
    admin_notes = Column(Text, nullable=True)
    processed_by = Column(BigInteger, nullable=True)  # Admin telegram ID
    
    # Indexes
    __table_args__ = (
        Index('idx_transaction_user_id', 'user_id'),
        Index('idx_transaction_status', 'status'),
        Index('idx_transaction_created_at', 'created_at'),
        Index('idx_transaction_reference', 'payment_reference'),
        Index('idx_transaction_order_id', 'order_id'),
        Index('idx_transaction_user_status', 'user_id', 'status'),
    )
    
    def __repr__(self):
        return f"<Transaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, type={self.type})>"


# ==================== PRICE CACHE MODEL ====================

class PriceCache(Base):
    """Cache for SMS-Man prices with profit markup applied"""
    __tablename__ = "price_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    country_id = Column(Integer, nullable=False)
    service_id = Column(Integer, nullable=False)
    
    # Pricing (with profit markup applied)
    original_cost = Column(Float, default=0.0)  # Cost from SMS-Man
    marked_up_cost = Column(Float, default=0.0)  # Cost to customer (with profit)
    profit = Column(Float, default=0.0)  # Markup amount
    
    # Availability
    available_count = Column(Integer, default=0)
    
    # Timestamps
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_price_cache_country_service', 'country_id', 'service_id', unique=True),
        Index('idx_price_cache_last_updated', 'last_updated'),
    )
    
    def __repr__(self):
        return f"<PriceCache(country={self.country_id}, service={self.service_id}, price={self.marked_up_cost})>"


# ==================== SUPPORT TICKET MODEL ====================

class SupportTicket(Base):
    """Support ticket model for user issues"""
    __tablename__ = "support_tickets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    
    # Ticket details
    subject = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(50), default="general")  # general, refund, technical, payment
    
    # Status
    status = Column(String(20), default="open")  # open, in_progress, resolved, closed
    priority = Column(String(10), default="normal")  # low, normal, high, urgent
    
    # Admin handling
    assigned_to = Column(BigInteger, nullable=True)  # Admin telegram ID
    admin_response = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_ticket_user_id', 'user_id'),
        Index('idx_ticket_status', 'status'),
        Index('idx_ticket_created_at', 'created_at'),
    )


# ==================== AUDIT LOG MODEL ====================

class AuditLog(Base):
    """Audit log for admin actions and important events"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Action details
    action = Column(String(100), nullable=False)  # e.g., "refund_processed", "balance_modified"
    entity_type = Column(String(50), nullable=True)  # e.g., "user", "order", "transaction"
    entity_id = Column(Integer, nullable=True)
    
    # Performer
    performed_by = Column(BigInteger, nullable=True)  # Admin or system
    performed_by_username = Column(String(100), nullable=True)
    
    # Details
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_action', 'action'),
        Index('idx_audit_performed_by', 'performed_by'),
        Index('idx_audit_created_at', 'created_at'),
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
    )


# ==================== SETTINGS MODEL ====================

class Setting(Base):
    """Application settings storage"""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, float, bool, json
    description = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(BigInteger, nullable=True)
    
    def get_value(self):
        """Get typed value based on value_type"""
        if self.value_type == "int":
            return int(self.value) if self.value else 0
        elif self.value_type == "float":
            return float(self.value) if self.value else 0.0
        elif self.value_type == "bool":
            return self.value.lower() == "true" if self.value else False
        elif self.value_type == "json":
            import json
            return json.loads(self.value) if self.value else {}
        else:
            return self.value or ""
    
    def set_value(self, value):
        """Set value with proper type conversion"""
        if self.value_type == "json":
            import json
            self.value = json.dumps(value)
        else:
            self.value = str(value)


# ==================== DAILY STATS MODEL ====================

class DailyStat(Base):
    """Daily statistics for analytics"""
    __tablename__ = "daily_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, unique=True, nullable=False)
    
    # User stats
    new_users = Column(Integer, default=0)
    total_users = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    
    # Order stats
    total_orders = Column(Integer, default=0)
    completed_orders = Column(Integer, default=0)
    cancelled_orders = Column(Integer, default=0)
    expired_orders = Column(Integer, default=0)
    
    # Revenue stats
    revenue = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    profit = Column(Float, default=0.0)
    
    # Payment stats
    paystack_deposits = Column(Float, default=0.0)
    crypto_deposits = Column(Float, default=0.0)
    telegram_deposits = Column(Float, default=0.0)
    
    # Refund stats
    refunds_issued = Column(Float, default=0.0)
    refund_count = Column(Integer, default=0)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_daily_stats_date', 'date'),
    )


# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    """Database manager for handling connections and sessions"""
    
    def __init__(self, database_url: str = None, pool_size: int = 20, max_overflow: int = 40):
        """
        Initialize database manager
        
        Args:
            database_url: PostgreSQL connection URL
            pool_size: Connection pool size
            max_overflow: Max overflow connections
        """
        if database_url is None:
            database_url = os.getenv('DATABASE_URL')
        
        if not database_url:
            raise ValueError("DATABASE_URL not provided and not found in environment")
        
        # Handle Railway's postgresql:// URL format
        if database_url.startswith("postgresql://"):
            # Ensure proper driver is used
            if "postgresql+psycopg2" not in database_url:
                database_url = database_url.replace("postgresql://", "postgresql+psycopg2://")
        
        logger.info(f"Initializing database connection to {database_url.split('@')[0]}@...")
        
        # Create engine with connection pooling
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,    # Recycle connections every hour
            echo=False,           # Set to True for SQL debugging
        )
        
        # Create session factory
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        logger.info("Database manager initialized successfully")
    
    def create_tables(self):
        """Create all tables if they don't exist"""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created/verified successfully")
            
            # Create default settings
            self._create_default_settings()
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def _create_default_settings(self):
        """Create default application settings"""
        session = self.get_session()
        try:
            # Check if settings exist
            default_settings = [
                {"key": "profit_margin", "value": "2.0", "value_type": "float", 
                 "description": "Profit markup multiplier (e.g., 2.0 = 2x price)"},
                {"key": "otp_timeout", "value": "300", "value_type": "int", 
                 "description": "OTP timeout in seconds"},
                {"key": "number_validity", "value": "600", "value_type": "int", 
                 "description": "Number validity in seconds"},
                {"key": "min_funding_usd", "value": "1.0", "value_type": "float", 
                 "description": "Minimum funding amount in USD"},
                {"key": "maintenance_mode", "value": "false", "value_type": "bool", 
                 "description": "Enable maintenance mode"},
                {"key": "referral_bonus_percent", "value": "10", "value_type": "int", 
                 "description": "Referral bonus percentage"},
            ]
            
            for setting_data in default_settings:
                existing = session.query(Setting).filter_by(key=setting_data["key"]).first()
                if not existing:
                    setting = Setting(**setting_data)
                    session.add(setting)
            
            session.commit()
            logger.info("Default settings created")
            
        except Exception as e:
            session.rollback()
            logger.warning(f"Error creating default settings: {e}")
        finally:
            session.close()
    
    def get_session(self):
        """Get a new database session"""
        return self.Session()
    
    def close_session(self):
        """Close the current scoped session"""
        self.Session.remove()
    
    def drop_all_tables(self):
        """Drop all tables (use with caution!)"""
        try:
            Base.metadata.drop_all(self.engine)
            logger.warning("All database tables dropped")
        except Exception as e:
            logger.error(f"Error dropping tables: {e}")
            raise
    
    def get_profit_stats(self):
        """Get profit statistics from orders"""
        session = self.get_session()
        try:
            from sqlalchemy import func
            
            result = session.query(
                func.sum(Order.cost).label('total_revenue'),
                func.sum(Order.original_cost).label('total_cost'),
                func.sum(Order.profit).label('total_profit'),
                func.count(Order.id).label('total_orders')
            ).filter(Order.status.in_([OrderStatus.RECEIVED, OrderStatus.ACTIVE])).first()
            
            return {
                'total_revenue': result[0] or 0,
                'total_cost': result[1] or 0,
                'total_profit': result[2] or 0,
                'total_orders': result[3] or 0,
            }
        finally:
            session.close()
    
    def get_user_count(self):
        """Get total user count"""
        session = self.get_session()
        try:
            return session.query(User).count()
        finally:
            session.close()
    
    def get_active_orders_count(self):
        """Get active orders count"""
        session = self.get_session()
        try:
            return session.query(Order).filter(
                Order.status == OrderStatus.ACTIVE
            ).count()
        finally:
            session.close()


# ==================== HELPER FUNCTIONS ====================

def get_profit_from_order(cost: float, original_cost: float) -> float:
    """Calculate profit from order"""
    return cost - original_cost

def get_profit_percent(cost: float, original_cost: float) -> float:
    """Calculate profit percentage"""
    if original_cost <= 0:
        return 0
    return ((cost - original_cost) / original_cost) * 100

def format_currency(amount: float, currency: str = "USD") -> str:
    """Format currency for display"""
    if currency == "USD":
        return f"${amount:.2f}"
    elif currency == "NGN":
        return f"₦{amount:,.2f}"
    else:
        return f"{amount:.2f}"

# ==================== EXPORTS ====================

__all__ = [
    'Base',
    'User',
    'Order',
    'Transaction',
    'PriceCache',
    'SupportTicket',
    'AuditLog',
    'Setting',
    'DailyStat',
    'TransactionType',
    'TransactionStatus',
    'OrderStatus',
    'PaymentMethod',
    'DatabaseManager',
    'get_profit_from_order',
    'get_profit_percent',
    'format_currency',
]
