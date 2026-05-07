"""
CRUD operations for DeuceVerify database
Provides all database interaction functions for users, transactions, orders, and payments
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from database.models import User, Transaction, Order, PaymentTransaction, TransactionType, OrderType, OrderStatus
import logging

logger = logging.getLogger(__name__)

# ============ USER FUNCTIONS ============

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    """Get user by Telegram ID"""
    try:
        return db.query(User).filter(User.telegram_id == telegram_id).first()
    except Exception as e:
        logger.error(f"Error getting user by telegram_id {telegram_id}: {e}")
        return None

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get user by database ID"""
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception as e:
        logger.error(f"Error getting user by id {user_id}: {e}")
        return None

def get_or_create_user(db: Session, telegram_id: int, username: str = None) -> User:
    """Get or create a user"""
    try:
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
            logger.info(f"✅ Created new user: {telegram_id} ({username})")
        elif username and user.username != username:
            # Update username if changed
            user.username = username
            db.commit()
            logger.info(f"Updated username for {telegram_id} to {username}")
        return user
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        db.rollback()
        raise

def update_user_balance(db: Session, user_id: int, amount: float, operation: str) -> User:
    """Update user balance with row lock for concurrency"""
    try:
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
    except Exception as e:
        logger.error(f"Error updating balance: {e}")
        db.rollback()
        raise

def update_user_username(db: Session, telegram_id: int, username: str) -> Optional[User]:
    """Update user's username"""
    try:
        user = get_user_by_telegram_id(db, telegram_id)
        if user:
            user.username = username
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            logger.info(f"Updated username for {telegram_id} to {username}")
        return user
    except Exception as e:
        logger.error(f"Error updating username: {e}")
        db.rollback()
        return None

def get_all_users(db: Session, limit: int = 100, offset: int = 0) -> List[User]:
    """Get all users with pagination"""
    try:
        return db.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

def get_user_count(db: Session) -> int:
    """Get total number of users"""
    try:
        return db.query(User).count()
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0

def get_admin_users(db: Session) -> List[User]:
    """Get all admin users"""
    try:
        return db.query(User).filter(User.is_admin == True).all()
    except Exception as e:
        logger.error(f"Error getting admin users: {e}")
        return []

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
    try:
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
    except Exception as e:
        logger.error(f"Error creating transaction: {e}")
        db.rollback()
        raise

def get_user_transactions(
    db: Session,
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> List[Transaction]:
    """Get user's transaction history"""
    try:
        return db.query(Transaction).filter(
            Transaction.user_id == user_id
        ).order_by(desc(Transaction.created_at)).offset(offset).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting user transactions: {e}")
        return []

def get_transaction_by_reference(db: Session, reference: str) -> Optional[Transaction]:
    """Get transaction by reference"""
    try:
        return db.query(Transaction).filter(Transaction.reference == reference).first()
    except Exception as e:
        logger.error(f"Error getting transaction by reference: {e}")
        return None

def get_all_transactions(db: Session, limit: int = 100, offset: int = 0) -> List[Transaction]:
    """Get all transactions with pagination"""
    try:
        return db.query(Transaction).order_by(desc(Transaction.created_at)).offset(offset).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting all transactions: {e}")
        return []

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
    try:
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
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        db.rollback()
        raise

def get_order(db: Session, order_id: int, user_id: int = None) -> Optional[Order]:
    """Get order by ID, optionally filtering by user"""
    try:
        query = db.query(Order).filter(Order.id == order_id)
        if user_id:
            query = query.filter(Order.user_id == user_id)
        return query.first()
    except Exception as e:
        logger.error(f"Error getting order {order_id}: {e}")
        return None

def get_order_by_request_id(db: Session, request_id: str) -> Optional[Order]:
    """Get order by SMS-Man request ID"""
    try:
        return db.query(Order).filter(Order.request_id == request_id).first()
    except Exception as e:
        logger.error(f"Error getting order by request_id: {e}")
        return None

def get_user_orders(
    db: Session,
    user_id: int,
    status: str = None,
    order_type: str = None,
    limit: int = 50,
    offset: int = 0
) -> List[Order]:
    """Get user's orders with filters"""
    try:
        query = db.query(Order).filter(Order.user_id == user_id)
        
        if status:
            query = query.filter(Order.status == OrderStatus(status))
        if order_type:
            query = query.filter(Order.order_type == OrderType(order_type))
        
        return query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        return []

def get_all_orders(db: Session, limit: int = 100, offset: int = 0) -> List[Order]:
    """Get all orders with pagination"""
    try:
        return db.query(Order).order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting all orders: {e}")
        return []

def update_order_status(
    db: Session,
    order_id: int,
    status: str,
    otp_code: str = None
) -> Optional[Order]:
    """Update order status and optionally OTP code"""
    try:
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
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        db.rollback()
        return None

def update_order_otp(db: Session, order_id: int, otp_code: str) -> Optional[Order]:
    """Update order's OTP code"""
    try:
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
    except Exception as e:
        logger.error(f"Error updating order OTP: {e}")
        db.rollback()
        return None

def get_active_orders(db: Session, user_id: int = None) -> List[Order]:
    """Get all active (non-expired, non-cancelled) orders"""
    try:
        query = db.query(Order).filter(
            Order.status.in_([OrderStatus.PENDING, OrderStatus.RECEIVED]),
            Order.expires_at > datetime.utcnow()
        )
        if user_id:
            query = query.filter(Order.user_id == user_id)
        return query.order_by(Order.created_at.desc()).all()
    except Exception as e:
        logger.error(f"Error getting active orders: {e}")
        return []

def get_expired_orders(db: Session) -> List[Order]:
    """Get orders that have expired but status not updated"""
    try:
        return db.query(Order).filter(
            Order.status == OrderStatus.PENDING,
            Order.expires_at <= datetime.utcnow()
        ).all()
    except Exception as e:
        logger.error(f"Error getting expired orders: {e}")
        return []

def cancel_order(db: Session, order_id: int, user_id: int = None) -> Optional[Order]:
    """Cancel an order"""
    try:
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
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        db.rollback()
        return None

def complete_order(db: Session, order_id: int) -> Optional[Order]:
    """Mark order as completed"""
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.status = OrderStatus.COMPLETED
            order.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(order)
            logger.info(f"Completed order {order_id}")
        return order
    except Exception as e:
        logger.error(f"Error completing order: {e}")
        db.rollback()
        return None

# ============ PAYMENT FUNCTIONS ============

def create_payment_transaction(
    db: Session,
    user_id: int,
    reference: str,
    amount: float,
    status: str = "pending"
) -> PaymentTransaction:
    """Create a payment transaction record"""
    try:
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
        logger.info(f"Created payment transaction: {reference} - ₦{amount}")
        return payment
    except Exception as e:
        logger.error(f"Error creating payment transaction: {e}")
        db.rollback()
        raise

def update_payment_transaction(
    db: Session,
    reference: str,
    status: str,
    paystack_data: Dict = None
) -> Optional[PaymentTransaction]:
    """Update payment transaction status"""
    try:
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
    except Exception as e:
        logger.error(f"Error updating payment transaction: {e}")
        db.rollback()
        return None

def get_payment_by_reference(db: Session, reference: str) -> Optional[PaymentTransaction]:
    """Get payment transaction by reference"""
    try:
        return db.query(PaymentTransaction).filter(PaymentTransaction.reference == reference).first()
    except Exception as e:
        logger.error(f"Error getting payment by reference: {e}")
        return None

def get_pending_payments(db: Session) -> List[PaymentTransaction]:
    """Get pending payment transactions"""
    try:
        return db.query(PaymentTransaction).filter(
            PaymentTransaction.status == "pending"
        ).all()
    except Exception as e:
        logger.error(f"Error getting pending payments: {e}")
        return []

def get_user_payments(db: Session, user_id: int, limit: int = 50) -> List[PaymentTransaction]:
    """Get user's payment transactions"""
    try:
        return db.query(PaymentTransaction).filter(
            PaymentTransaction.user_id == user_id
        ).order_by(desc(PaymentTransaction.created_at)).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting user payments: {e}")
        return []

# ============ STATS FUNCTIONS ============

def get_user_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Get user statistics"""
    try:
        total_orders = db.query(Order).filter(Order.user_id == user_id).count()
        active_orders = db.query(Order).filter(
            Order.user_id == user_id,
            Order.status.in_([OrderStatus.PENDING, OrderStatus.RECEIVED])
        ).count()
        
        total_spent = db.query(func.sum(Order.cost)).filter(
            Order.user_id == user_id,
            Order.status == OrderStatus.COMPLETED
        ).scalar() or 0
        
        total_deposits = db.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.CREDIT,
            Transaction.status == "completed"
        ).scalar() or 0
        
        return {
            "total_orders": total_orders,
            "active_orders": active_orders,
            "total_spent": float(total_spent),
            "total_deposits": float(total_deposits)
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {
            "total_orders": 0,
            "active_orders": 0,
            "total_spent": 0.0,
            "total_deposits": 0.0
        }

def get_admin_stats(db: Session) -> Dict[str, Any]:
    """Get admin statistics"""
    try:
        total_users = db.query(User).count()
        total_orders = db.query(Order).count()
        active_orders = db.query(Order).filter(
            Order.status.in_([OrderStatus.PENDING, OrderStatus.RECEIVED])
        ).count()
        
        total_volume = db.query(func.sum(Order.cost)).filter(
            Order.status.in_([OrderStatus.COMPLETED, OrderStatus.RECEIVED])
        ).scalar() or 0
        
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = db.query(Order).filter(Order.created_at >= today).count()
        today_volume = db.query(func.sum(Order.cost)).filter(
            Order.created_at >= today,
            Order.status.in_([OrderStatus.COMPLETED, OrderStatus.RECEIVED])
        ).scalar() or 0
        
        pending_orders = db.query(Order).filter(Order.status == OrderStatus.PENDING).count()
        received_orders = db.query(Order).filter(Order.status == OrderStatus.RECEIVED).count()
        expired_orders = db.query(Order).filter(Order.status == OrderStatus.EXPIRED).count()
        cancelled_orders = db.query(Order).filter(Order.status == OrderStatus.CANCELLED).count()
        
        return {
            "total_users": total_users,
            "total_orders": total_orders,
            "active_orders": active_orders,
            "total_volume": float(total_volume),
            "today_orders": today_orders,
            "today_volume": float(today_volume),
            "pending_orders": pending_orders,
            "received_orders": received_orders,
            "expired_orders": expired_orders,
            "cancelled_orders": cancelled_orders
        }
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        return {
            "total_users": 0,
            "total_orders": 0,
            "active_orders": 0,
            "total_volume": 0.0,
            "today_orders": 0,
            "today_volume": 0.0,
            "pending_orders": 0,
            "received_orders": 0,
            "expired_orders": 0,
            "cancelled_orders": 0
        }

def get_orders_by_status(db: Session, status: str) -> List[Order]:
    """Get all orders with specific status"""
    try:
        return db.query(Order).filter(Order.status == OrderStatus(status)).all()
    except Exception as e:
        logger.error(f"Error getting orders by status: {e}")
        return []

def get_orders_by_date_range(db: Session, start_date: datetime, end_date: datetime) -> List[Order]:
    """Get orders within date range"""
    try:
        return db.query(Order).filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date
        ).order_by(Order.created_at.desc()).all()
    except Exception as e:
        logger.error(f"Error getting orders by date range: {e}")
        return []

# ============ BULK OPERATIONS ============

def expire_pending_orders(db: Session) -> int:
    """Expire all pending orders that have passed expiry date"""
    try:
        expired_orders = db.query(Order).filter(
            Order.status == OrderStatus.PENDING,
            Order.expires_at <= datetime.utcnow()
        ).all()
        
        count = 0
        for order in expired_orders:
            order.status = OrderStatus.EXPIRED
            order.updated_at = datetime.utcnow()
            count += 1
        
        if count > 0:
            db.commit()
            logger.info(f"Expired {count} orders")
        return count
    except Exception as e:
        logger.error(f"Error expiring pending orders: {e}")
        db.rollback()
        return 0

def delete_old_completed_orders(db: Session, days: int = 30) -> int:
    """Delete completed orders older than specified days"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        deleted = db.query(Order).filter(
            Order.status.in_([OrderStatus.COMPLETED, OrderStatus.EXPIRED, OrderStatus.CANCELLED]),
            Order.created_at <= cutoff_date
        ).delete()
        
        db.commit()
        logger.info(f"Deleted {deleted} old orders")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting old orders: {e}")
        db.rollback()
        return 0
