from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    specialization = Column(String)


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, unique=True, nullable=False)

    current_doctor_id = Column(Integer, ForeignKey("doctors.id"))
    status = Column(String, default="active")
    status_note = Column(String, default="")
    doctor = relationship("Doctor")


class Content(Base):
    __tablename__ = "content"
    id = Column(Integer, primary_key=True)
    type = Column(String)
    text = Column(String)
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
