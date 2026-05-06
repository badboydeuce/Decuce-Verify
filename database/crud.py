from sqlalchemy.orm import Session
from database.models import User, Transaction, Order, PaymentTransaction
from datetime import datetime
from typing import Optional, List

async def get_or_create_user(db: Session, telegram_id: int, username: str = None) -> User:
    """Get or create a user"""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def update_balance(db: Session, user_id: int, amount: float, operation: str) -> User:
    """Update user balance"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        if operation == "credit":
            user.balance += amount
        elif operation == "debit":
            if user.balance >= amount:
                user.balance -= amount
            else:
                raise ValueError("Insufficient balance")
        db.commit()
        db.refresh(user)
    return user

def create_order(db: Session, **kwargs) -> Order:
    """Create a new order"""
    order = Order(**kwargs)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order

def get_user_orders(db: Session, user_id: int, status: str = None) -> List[Order]:
    """Get user's orders"""
    query = db.query(Order).filter(Order.user_id == user_id)
    if status:
        query = query.filter(Order.status == status)
    return query.order_by(Order.created_at.desc()).all()

def get_order(db: Session, order_id: int, user_id: int) -> Optional[Order]:
    """Get specific order"""
    return db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
