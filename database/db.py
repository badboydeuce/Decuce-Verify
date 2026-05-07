"""
Database connection and initialization
"""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from config import settings
from database.models import Base
import logging

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database tables - creates all tables if they don't exist"""
    try:
        # Check if tables exist
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        logger.info(f"Existing tables: {existing_tables}")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        # Verify tables were created
        inspector = inspect(engine)
        tables_after = inspector.get_table_names()
        logger.info(f"Tables after creation: {tables_after}")
        
        # Check if users table exists
        if 'users' not in tables_after:
            logger.error("❌ Users table was not created!")
            raise Exception("Users table creation failed")
        
        logger.info("✅ Database tables initialized successfully")
        
        # Optional: Create default admin user
        _create_default_admin()
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

def _create_default_admin():
    """Create default admin user if not exists"""
    from database.crud import get_user_by_telegram_id, get_or_create_user
    
    db = SessionLocal()
    try:
        for admin_id in settings.admin_ids:
            user = get_user_by_telegram_id(db, admin_id)
            if not user:
                user = get_or_create_user(db, admin_id, username=f"admin_{admin_id}")
                user.is_admin = True
                db.commit()
                logger.info(f"✅ Created admin user: {admin_id}")
            elif not user.is_admin:
                user.is_admin = True
                db.commit()
                logger.info(f"✅ Updated user {admin_id} to admin")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
    finally:
        db.close()

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
