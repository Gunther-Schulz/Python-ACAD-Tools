"""Web service configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Literal
from src.core.types import StyleName

ServiceType = Literal["wmts", "wms"]

@dataclass
class WebServiceConfig:
    """Configuration for a web map service."""
    name: str
    type: ServiceType
    url: str
    layer: str
    crs: str
    style: Optional[StyleName] = None
    format: str = "image/png"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebServiceConfig':
        """Create WebServiceConfig from dictionary."""
        service_type = data['type']
        if service_type not in ("wmts", "wms"):
            raise ValueError(f"Invalid service type: {service_type}")
            
        return cls(
            name=data['name'],
            type=service_type,
            url=data['url'],
            layer=data['layer'],
            crs=data['crs'],
            style=data.get('style'),
            format=data.get('format', "image/png")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'name': self.name,
            'type': self.type,
            'url': self.url,
            'layer': self.layer,
            'crs': self.crs,
            'format': self.format
        }
        if self.style:
            result['style'] = self.style
        return result

@dataclass
class WebServicesConfig:
    """Configuration for all web services."""
    services: List[WebServiceConfig]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebServicesConfig':
        """Create WebServicesConfig from dictionary."""
        return cls(
            services=[WebServiceConfig.from_dict(service) for service in data.get('services', [])]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'services': [service.to_dict() for service in self.services]
        } 