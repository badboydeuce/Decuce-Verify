# Initialize DB
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

def init():
    db = DatabaseManager(os.getenv('DATABASE_URL'))
    db.create_tables()
    print("✅ Database tables created successfully!")

if __name__ == "__main__":
    init()
