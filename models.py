from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()
engine = create_engine('sqlite:///tgtg.db')
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'

    chat_id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    access_token = Column(String)
    refresh_token = Column(String)
    cookie = Column(String)
    notified_bags = relationship("NotifiedBag", back_populates="user", cascade="all, delete-orphan")

class NotifiedBag(Base):
    __tablename__ = 'notified_bags'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('users.chat_id'))
    item_id = Column(String)
    user = relationship("User", back_populates="notified_bags")

def init_db():
    Base.metadata.create_all(engine)
