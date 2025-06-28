"""
Routes package for Learning Observer Flask Application.

This package contains all the route blueprints for different user roles.
"""

# Import blueprint modules
from . import auth
from .auth import auth_bp

from . import admin
from .admin import admin_bp

from . import observer
from .observer import observer_bp

from . import parent
from .parent import parent_bp

__all__ = [
    # Blueprint modules
    'auth',
    'admin',
    'observer',
    'parent',
    # Blueprint objects
    'auth_bp',
    'admin_bp',
    'observer_bp',
    'parent_bp'
]
