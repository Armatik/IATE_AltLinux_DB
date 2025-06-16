# models.py

from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Package(Base):
    __tablename__ = 'packages'
    package_id  = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=False)

    architectures = relationship('PackageArchitecture', back_populates='package', cascade='all, delete-orphan')
    updates       = relationship('PackageUpdate', back_populates='package', cascade='all, delete-orphan')
    acl_entries   = relationship('ACL', back_populates='package', cascade='all, delete-orphan')
    groups        = relationship('PackageGroup', back_populates='package', cascade='all, delete-orphan')
    reports       = relationship('Report', back_populates='package', cascade='all, delete-orphan')

class Maintainer(Base):
    __tablename__ = 'maintainers'
    maintainer_id = Column(Integer, primary_key=True, autoincrement=True)
    nickname      = Column(String(50), nullable=False, unique=True)
    full_name     = Column(String(100), nullable=False)

    updates = relationship('PackageUpdate', back_populates='updater', cascade='all, delete-orphan')
    reports = relationship('Report', back_populates='assignee', cascade='all, delete-orphan')

class ACL(Base):
    __tablename__ = 'acl'
    acl_id        = Column(Integer, primary_key=True, autoincrement=True)
    package_id    = Column(Integer, ForeignKey('packages.package_id'), nullable=False)
    maintainer_id = Column(Integer, ForeignKey('maintainers.maintainer_id'), nullable=False)
    role          = Column(String(50), nullable=False)

    package    = relationship('Package', back_populates='acl_entries')
    maintainer = relationship('Maintainer')

class PackageArchitecture(Base):
    __tablename__   = 'architectures'
    arch_id         = Column(Integer, primary_key=True, autoincrement=True)
    package_id      = Column(Integer, ForeignKey('packages.package_id'), nullable=False)
    architecture    = Column(String(50), nullable=False)

    package = relationship('Package', back_populates='architectures')

class PackageUpdate(Base):
    __tablename__   = 'package_updates'
    update_id       = Column(Integer, primary_key=True, autoincrement=True)
    package_id      = Column(Integer, ForeignKey('packages.package_id'), nullable=False)
    updater_id      = Column(Integer, ForeignKey('maintainers.maintainer_id'), nullable=False)
    update_version  = Column(String(50), nullable=False)
    update_date     = Column(Date, nullable=False)
    changelog       = Column(Text, nullable=False)

    package = relationship('Package', back_populates='updates')
    updater = relationship('Maintainer', back_populates='updates')

class PackageGroup(Base):
    __tablename__ = 'package_groups'
    group_id    = Column(Integer, primary_key=True, autoincrement=True)
    group_name  = Column(String(100), nullable=False)
    package_id  = Column(Integer, ForeignKey('packages.package_id'), nullable=False)

    package = relationship('Package', back_populates='groups')

class Report(Base):
    __tablename__   = 'reports'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    package_id      = Column(Integer, ForeignKey('packages.package_id'), nullable=False)
    status          = Column(String(20), nullable=False)
    resolution      = Column(String(20), nullable=False)
    assignee_id     = Column(Integer, ForeignKey('maintainers.maintainer_id'), nullable=False)
    reporter        = Column(String(100), nullable=False)
    summary         = Column(Text, nullable=False)
    last_changed    = Column(Date)

    package  = relationship('Package', back_populates='reports')
    assignee = relationship('Maintainer', back_populates='reports')
