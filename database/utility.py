import os
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from database.entity import *


class database:
    def __init__(self):
        USER = os.getenv("DB_USER", "appuser")
        PASS = os.getenv("DB_PASSWORD", "secret")
        HOST = os.getenv("DB_ADDR", "127.0.0.1")
        PORT = int(os.getenv("DB_PORT", "3306"))
        DB   = os.getenv("DB_NAME", "insurehub") 
        self.url = f"mysql+pymysql://{USER}:{PASS}@{HOST}:{PORT}/{DB}"
        self.engine = create_engine(self.url, pool_pre_ping=True, pool_recycle=1800, future=True)
        Base.metadata.create_all(self.engine)



if __name__ == "__main__":
    db = database()
    with Session(db.engine) as session:
        file = CryptolFile(
            filename="test/test",
            content="THIS IS A TEST"
        )
        session.add(file)
        session.commit()



