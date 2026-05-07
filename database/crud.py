from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from database.models import User, Transaction, Order, PaymentTransaction, TransactionType, OrderType, OrderStatus
import logging

logger = logging.getLogger(__name__)

# ============ USER FUNCTIONS ============

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    """Get user by Telegram ID"""
    return db.query(User).filter(User.telegram_id == telegram_id).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get user by database ID"""
    return db.query(User).filter(User.id == user_id).first()

def get_or_create_user(db: Session, telegram_id: int, username: str = None) -> User:
    """Get or create a user"""
    user = get_user_by_telegram_id(db, telegram_id)
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            balance=0.0,
            is_admin=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {telegram_id} ({username})")
    return user

def update_user_balance(db: Session, user_id: int, amount: float, operation: str) -> User:
    """Update user balance with row lock for concurrency"""
    # Use row-level lock to prevent race conditions
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    if operation == "credit":
        user.balance += amount
        logger.info(f"Credited {amount} to user {user.telegram_id}. New balance: {user.balance}")
    elif operation == "debit":
        if user.balance >= amount:
            user.balance -= amount
            logger.info(f"Debited {amount} from user {user.telegram_id}. New balance: {user.balance}")
        else:
            raise ValueError(f"Insufficient balance. Required: {amount}, Available: {user.balance}")
    else:
        raise ValueError(f"Invalid operation: {operation}")
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

def update_user_username(db: Session, telegram_id: int, username: str) -> Optional[User]:
    """Update user's username"""
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        user.username = username
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
    return user

def get_all_users(db: Session, limit: int = 100, offset: int = 0) -> List[User]:
    """Get all users with pagination"""
    return db.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()

def get_user_count(db: Session) -> int:
    """Get total number of users"""
    return db.query(User).count()

# ============ TRANSACTION FUNCTIONS ============

def create_transaction(
    db: Session,
    user_id: int,
    amount: float,
    transaction_type: str,
    reference: str = None,
    description: str = None,
    status: str = "completed"
) -> Transaction:
    """Create a transaction record"""
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        type=TransactionType(transaction_type),
        reference=reference,
        description=description,
        status=status,
        created_at=datetime.utcnow()
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    logger.info(f"Created {transaction_type} transaction: {amount} for user {user_id}")
    return transaction

def get_user_transactions(
    db: Session,
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> List[Transaction]:
    """Get user's transaction history"""
    return db.query(Transaction).filter(
        Transaction.user_id == user_id
    ).order_by(desc(Transaction.created_at)).offset(offset).limit(limit).all()

def get_transaction_by_reference(db: Session, reference: str) -> Optional[Transaction]:
    """Get transaction by reference"""
    return db.query(Transaction).filter(Transaction.reference == reference).first()

# ============ ORDER FUNCTIONS ============

def create_order(
    db: Session,
    user_id: int,
    order_type: str,
    service_id: str,
    service_name: str,
    country_id: str,
    country_name: str,
    number: str,
    request_id: str,
    cost: float,
    expires_at: datetime,
    rental_duration: str = None
) -> Order:
    """Create a new order"""
    order = Order(
        user_id=user_id,
        order_type=OrderType(order_type),
        service_id=service_id,
        service_name=service_name,
        country_id=country_id,
        country_name=country_name,
        number=number,
        request_id=request_id,
        cost=cost,
        status=OrderStatus.PENDING,
        expires_at=expires_at,
        rental_duration=rental_duration,
        created_at=datetime.utcnow()
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    logger.info(f"Created {order_type} order {order.id} for user {user_id}")
    return order

def get_order(db: Session, order_id: int, user_id: int = None) -> Optional[Order]:
    """Get order by ID, optionally filtering by user"""
    query = db.query(Order).filter(Order.id == order_id)
    if user_id:
        query = query.filter(Order.user_id == user_id)
    return query.first()

def get_user_orders(
    db: Session,
    user_id: int,
    status: str = None,
    order_type: str = None,
    limit: int = 50
) -> List[Order]:
    """Get user's orders with filters"""
    query = db.query(Order).filter(Order.user_id == user_id)
    
    if status:
        query = query.filter(Order.status == OrderStatus(status))
    if order_type:
        query = query.filter(Order.order_type == OrderType(order_type))
    
    return query.order_by(desc(Order.created_at)).limit(limit).all()

def update_order_status(
    db: Session,
    order_id: int,
    status: str,
    otp_code: str = None
) -> Optional[Order]:
    """Update order status and optionally OTP code"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.status = OrderStatus(status)
        order.updated_at = datetime.utcnow()
        if otp_code:
            order.otp_code = otp_code
        db.commit()
        db.refresh(order)
        logger.info(f"Updated order {order_id} status to {status}")
    return order

def update_order_otp(db: Session, order_id: int, otp_code: str) -> Optional[Order]:
    """Update order's OTP code"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.otp_code = otp_code
        order.updated_at = datetime.utcnow()
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.RECEIVED
        db.commit()
        db.refresh(order)
        logger.info(f"Updated OTP for order {order_id}: {otp_code}")
    return order

def get_active_orders(db: Session, user_id: int = None) -> List[Order]:
    """Get all active (non-expired, non-cancelled) orders"""
    query = db.query(Order).filter(
        Order.status.in_([OrderStatus.PENDING, OrderStatus.RECEIVED]),
        Order.expires_at > datetime.utcnow()
    )
    if user_id:
        query = query.filter(Order.user_id == user_id)
    return query.order_by(Order.created_at.desc()).all()

def get_expired_orders(db: Session) -> List[Order]:
    """Get orders that have expired but status not updated"""
    return db.query(Order).filter(
        Order.status == OrderStatus.PENDING,
        Order.expires_at <= datetime.utcnow()
    ).all()

def cancel_order(db: Session, order_id: int, user_id: int = None) -> Optional[Order]:
    """Cancel an order"""
    query = db.query(Order).filter(Order.id == order_id)
    if user_id:
        query = query.filter(Order.user_id == user_id)
    
    order = query.first()
    if order and order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
        logger.info(f"Cancelled order {order_id}")
    return order

# ============ PAYMENT FUNCTIONS ============

def create_payment_transaction(
    db: Session,
    user_id: int,
    reference: str,
    amount: float,
    status: str = "pending"
) -> PaymentTransaction:
    """Create a payment transaction record"""
    payment = PaymentTransaction(
        user_id=user_id,
        reference=reference,
        amount=amount,
        status=status,
        created_at=datetime.utcnow()
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment

def update_payment_transaction(
    db: Session,
    reference: str,
    status: str,
    paystack_data: Dict = None
) -> Optional[PaymentTransaction]:
    """Update payment transaction status"""
    payment = db.query(PaymentTransaction).filter(PaymentTransaction.reference == reference).first()
    if payment:
        payment.status = status
        if status == "completed":
            payment.completed_at = datetime.utcnow()
        if paystack_data:
            import json
            payment.paystack_data = json.dumps(paystack_data)
        db.commit()
        db.refresh(payment)
        logger.info(f"Updated payment {reference} status to {status}")
    return payment

def get_pending_payments(db: Session) -> List[PaymentTransaction]:
    """Get pending payment transactions"""
    return db.query(PaymentTransaction).filter(
        PaymentTransaction.status == "pending"
    ).all()

# ============ STATS FUNCTIONS ============

def get_user_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Get user statistics"""
    total_orders = db.query(Order).filter(Order.user_id == user_id).count()
    active_orders = db.query(Order).filter(
        Order.user_id == user_id,
        Order.status.in_([OrderStatus.PENDING, OrderStatus.RECEIVED])
    ).count()
    
    total_spent = db.query(Order).filter(
        Order.user_id == user_id,
        Order.status == OrderStatus.COMPLETED
    ).with_entities(db.func.sum(Order.cost)).scalar() or 0
    
    return {
        "total_orders": total_orders,
        "active_orders": active_orders,
        "total_spent": total_spent
    }

def get_admin_stats(db: Session) -> Dict[str, Any]:
    """Get admin statistics"""
    total_users = db.query(User).count()
    total_orders = db.query(Order).count()
    active_orders = db.query(Order).filter(
        Order.status.in_([OrderStatus.PENDING, OrderStatus.RECEIVED])
    ).count()
    
    total_volume = db.query(Order).filter(
        Order.status == OrderStatus.COMPLETED
    ).with_entities(db.func.sum(Order.cost)).scalar() or 0
    
    return {
        "total_users": total_users,
        "total_orders": total_orders,
        "active_orders": active_orders,
        "total_volume": total_volume
    }
