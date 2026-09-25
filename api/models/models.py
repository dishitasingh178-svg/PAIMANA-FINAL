
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Text, Numeric, Date, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class Project(Base):
    __tablename__ = "projects"

    project_id = Column(String(50), primary_key=True, index=True)
    project_name = Column(Text, nullable=False)
    sector = Column(String(100))
    implementing_agency = Column(String(100))
    state = Column(String(100))
    date_of_approval = Column(Date)
    original_cost_crore = Column(Numeric(14, 2))
    original_commissioning_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships to child tables
    updates = relationship("ProjectUpdate", back_populates="project", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="project", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="project", cascade="all, delete-orphan")


class ProjectUpdate(Base):
    __tablename__ = "project_updates"

    id = Column(BigInteger, primary_key=True, index=True)
    project_id = Column(String(50), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    report_month = Column(String(7), nullable=False)
    serial_no = Column(Integer)
    revised_cost_crore = Column(Numeric(14, 2))
    anticipated_cost_crore = Column(Numeric(14, 2))
    cumulative_expenditure_crore = Column(Numeric(14, 2))
    revised_commissioning_date = Column(Date)
    anticipated_commissioning_date = Column(Date)
    delay_original_months = Column(Numeric(8, 2))
    delay_revised_months = Column(Numeric(8, 2))
    milestones_achieved = Column(Integer)
    milestones_total = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("Project", back_populates="updates")
    __table_args__ = (UniqueConstraint("project_id", "report_month", name="unique_project_report"),)


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id = Column(BigInteger, primary_key=True, index=True)
    project_id = Column(String(50), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    report_month = Column(String(7), nullable=False)
    cost_risk_probability = Column(Numeric(6, 4), nullable=False)
    schedule_risk_probability = Column(Numeric(6, 4), nullable=False)
    cox_risk = Column(Numeric(10, 4), nullable=False)
    cox_risk_probability = Column(Numeric(6, 4), nullable=False)
    composite_risk_score = Column(Numeric(5, 2), nullable=False)
    risk_tier = Column(String(20), nullable=False)
    model_version = Column(String(50), default="1.0.0")
    generated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("Project", back_populates="predictions")


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(BigInteger, primary_key=True, index=True)
    project_id = Column(String(50), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False)
    status = Column(String(20), nullable=False, default="NEW", server_default="NEW")
    status_updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    acknowledged_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    dismissed_at = Column(DateTime(timezone=True))
    review_note = Column(Text)
    triggered_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    project = relationship("Project", back_populates="alerts")
