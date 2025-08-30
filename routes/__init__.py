"""
Routes package for Guard Management System
"""

from .auth_routes import auth_router
from .admin_routes_working import admin_router

__all__ = [
    "auth_router",
    "admin_router"
] 