from typing import List
from typing import Optional
from sqlalchemy import ForeignKey
from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.dialects.mysql import LONGTEXT

class Base(DeclarativeBase):
    pass

class CryptolFile(Base):
    __tablename__ = "cryptol_file"

    __table_args__ = (
        # Optional FULLTEXT index (requires InnoDB + appropriate MariaDB version)
        # Index("ix_cryptol_file_content_fts", "content", mysql_prefix="FULLTEXT"),
        {
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_bin",
        },
    )

    file_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    # Store UTF-8 text as LONGTEXT with binary collation to preserve exact bytes
    content: Mapped[str] = mapped_column(LONGTEXT(collation="utf8mb4_bin"), nullable=False)


    def __repr__(self):
        return f"<cryptol_file(file_id={self.file_id}, filename='{self.filename}', content='{self.content}')>"
