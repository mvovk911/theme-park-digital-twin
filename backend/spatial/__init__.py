"""Read-only spatial design API; intentionally independent of live operations."""
from .api import install_spatial_routes
from .contracts import RouteRequest
from .service import SpatialIdentityError, SpatialService

__all__ = ['install_spatial_routes', 'RouteRequest', 'SpatialIdentityError', 'SpatialService']
