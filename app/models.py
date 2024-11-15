from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Job(Base):
    __tablename__ = 'job'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    number = Column(String(256), nullable=True)
    name = Column(String(256), nullable=False)
    time = Column(DateTime, nullable=True)
    level = Column(String(256), nullable=True)
    status = Column(String(256), nullable=False,default='待办')
    checks = relationship("Check", back_populates="job")

class Check(Base):
    __tablename__ = 'check'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    number = Column(String(256), nullable=True)
    name = Column(String(256), nullable=False)
    check_time = Column(DateTime, nullable=True)
    countdown = Column(String(8), nullable=True)
    check_group = Column(String(256), nullable=False)
    job_id = Column(Integer, ForeignKey('job.id'), nullable=False)
    execution = Column(String(256), nullable=False)
    status = Column(Integer, nullable=False, default=0)

    job = relationship("Job", back_populates="checks")
