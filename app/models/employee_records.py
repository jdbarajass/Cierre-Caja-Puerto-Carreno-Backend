"""
Modelos para Control de Empleadas.
El campo nombre_empleada es texto libre (no FK a usuarios) para identificar
a qué persona corresponde cada registro cuando varias comparten la misma cuenta.
"""
from datetime import datetime
from app.models.user import db


class EmployeeClothing(db.Model):
    __tablename__ = 'employee_clothing'

    id = db.Column(db.Integer, primary_key=True)
    nombre_empleada = db.Column(db.String(100), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    product = db.Column(db.String(255), nullable=False)
    value = db.Column(db.Float, nullable=False)
    discount_pct = db.Column(db.Float, nullable=False, default=0)
    final_value = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_empleada': self.nombre_empleada,
            'date': self.date.isoformat() if self.date else None,
            'product': self.product,
            'value': self.value,
            'discount_pct': self.discount_pct,
            'final_value': self.final_value,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class EmployeeLoan(db.Model):
    __tablename__ = 'employee_loans'

    id = db.Column(db.Integer, primary_key=True)
    nombre_empleada = db.Column(db.String(100), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_empleada': self.nombre_empleada,
            'date': self.date.isoformat() if self.date else None,
            'amount': self.amount,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class EmployeePermission(db.Model):
    __tablename__ = 'employee_permissions'

    TYPES = ['permiso', 'incapacidad', 'llegada_tarde', 'salida_temprana']

    id = db.Column(db.Integer, primary_key=True)
    nombre_empleada = db.Column(db.String(100), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=True)
    hours = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_empleada': self.nombre_empleada,
            'date': self.date.isoformat() if self.date else None,
            'type': self.type,
            'description': self.description,
            'hours': self.hours,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class EmployeeVacation(db.Model):
    __tablename__ = 'employee_vacations'

    id = db.Column(db.Integer, primary_key=True)
    nombre_empleada = db.Column(db.String(100), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_empleada': self.nombre_empleada,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'days': self.days,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class EmployeePayment(db.Model):
    __tablename__ = 'employee_payments'

    TYPES = ['quincena', 'prima', 'comision', 'otro']

    id = db.Column(db.Integer, primary_key=True)
    nombre_empleada = db.Column(db.String(100), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    type = db.Column(db.String(30), nullable=False, default='quincena')
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_empleada': self.nombre_empleada,
            'date': self.date.isoformat() if self.date else None,
            'type': self.type,
            'amount': self.amount,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
