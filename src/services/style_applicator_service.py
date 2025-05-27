"""Concrete implementation of the IStyleApplicator interface.
This service now primarily orchestrates calls to specialized services for DXF resource management,
geometry processing, and style application/resolution.
"""
from typing import Optional, Any, Dict, Union # Union might be removable if complex types are gone

import geopandas as gpd
# import pandas as pd # Not directly used anymore
# import ezdxf # Not directly used anymore

from ezdxf.document import Drawing # Still needed for type hints in public interface
from ezdxf.entities import DXFGraphic # Still needed for type hints in public interface
# from ezdxf.layouts import Modelspace # No longer directly used
# from ezdxf.lldxf.const import BYLAYER, BYBLOCK, LINEWEIGHT_BYLAYER, LINEWEIGHT_DEFAULT # No longer directly used
# from ezdxf.math import Vec3, Z_AXIS # No longer directly used
# from ezdxf.enums import MTextEntityAlignment # No longer directly used

from ..interfaces.style_applicator_interface import IStyleApplicator
from ..interfaces.logging_service_interface import ILoggingService
# from ..interfaces.config_loader_interface import IConfigLoader # REMOVED if ACI map moved
from ..interfaces.dxf_adapter_interface import IDXFAdapter # Still needed for is_available()
from ..interfaces.dxf_resource_manager_interface import IDXFResourceManager # Potentially for direct calls if any remain
from ..interfaces.geometry_processor_interface import IGeometryProcessor
from ..interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator # ADDED
from ..domain.config_models import (
    StyleConfig, NamedStyle, GeomLayerDefinition,
    # LayerStyleProperties, TextStyleProperties, HatchStyleProperties, AciColorMappingItem # No longer directly used
)
from ..domain.exceptions import ProcessingError, DXFProcessingError # ConfigError might be removable

# DEFAULT_ACI_COLOR = 7 # REMOVED, belongs to orchestrator
# DEFAULT_LINETYPE = "Continuous" # REMOVED, belongs to orchestrator

class StyleApplicatorService(IStyleApplicator):
    """Service for applying styles to geometric data and DXF entities.
    Delegates most work to specialized services.
    """

    def __init__(
        self,
        logger_service: ILoggingService,
        dxf_adapter: IDXFAdapter, # For is_available()
        dxf_resource_manager: IDXFResourceManager, # Pass-through or direct use if any
        geometry_processor: IGeometryProcessor,
        style_orchestrator: IStyleApplicationOrchestrator # ADDED
        # config_loader: IConfigLoader, # REMOVED if ACI map moved
    ):
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)
        self._dxf_adapter = dxf_adapter # For is_available()
        self._dxf_resource_manager = dxf_resource_manager # Retained if needed by any thin method, or for future use
        self._geometry_processor = geometry_processor
        self._style_orchestrator = style_orchestrator # STORED
        # self._aci_map: Optional[Dict[str, int]] = None # REMOVED, moved to orchestrator

        if not self._dxf_adapter.is_available():
            self._logger.error("ezdxf library not available via adapter. DXF functionality will be severely limited.")

    # --- Methods delegated to StyleApplicationOrchestratorService ---

    def get_style_for_layer(
        self,
        layer_name: str,
        layer_definition: Optional[GeomLayerDefinition],
        style_config: StyleConfig
    ) -> Optional[NamedStyle]:
        self._logger.debug(f"Delegating get_style_for_layer for '{layer_name}' to orchestrator.")
        return self._style_orchestrator.get_style_for_layer(
            layer_name, layer_definition, style_config
        )

    def apply_style_to_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        style: NamedStyle,
        layer_name: str
    ) -> gpd.GeoDataFrame:
        self._logger.debug(f"Delegating apply_style_to_geodataframe for '{layer_name}' to orchestrator.")
        return self._style_orchestrator.apply_style_to_geodataframe(
            gdf, style, layer_name
        )

    def apply_style_to_dxf_entity(
        self,
        entity: DXFGraphic,
        style: NamedStyle,
        dxf_drawing: Drawing
    ) -> None:
        if not self._dxf_adapter.is_available(): # Keep basic check before delegation
            raise DXFProcessingError("DXF adapter not available.")
        self._logger.debug(f"Delegating apply_style_to_dxf_entity for {entity.dxf.handle if hasattr(entity, 'dxf') else 'N/A'} to orchestrator.")
        self._style_orchestrator.apply_style_to_dxf_entity(
            entity, style, dxf_drawing
        )

    def apply_styles_to_dxf_layer(
        self,
        dxf_drawing: Drawing,
        layer_name: str,
        style: NamedStyle
    ) -> None:
        if not self._dxf_adapter.is_available(): # Keep basic check
            raise DXFProcessingError("DXF adapter not available.")
        self._logger.debug(f"Delegating apply_styles_to_dxf_layer for '{layer_name}' to orchestrator.")
        self._style_orchestrator.apply_styles_to_dxf_layer(
            dxf_drawing, layer_name, style
        )

    # --- Methods delegated to GeometryProcessorService (already done) ---
    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
        self._logger.debug(f"Delegating add_geodataframe_to_dxf for layer '{layer_name}' to GeometryProcessorService.")
        if not self._dxf_adapter.is_available():
            raise DXFProcessingError("Cannot add geometries to DXF: ezdxf library not available via adapter.")
        self._geometry_processor.add_geodataframe_to_dxf(
            dxf_drawing=dxf_drawing,
            gdf=gdf,
            layer_name=layer_name,
            style=style,
            layer_definition=layer_definition
        )

    # --- Cache Management (delegated or removed if ACI map moved) ---
    def clear_caches(self) -> None:
        """Clears caches, potentially by delegating to the style orchestrator."""
        self._logger.debug("Delegating clear_caches to style orchestrator.")
        self._style_orchestrator.clear_caches()

    def get_cache_info(self) -> Dict[str, Any]: # Return type matches orchestrator
        """Gets cache info, potentially by delegating to the style orchestrator."""
        self._logger.debug("Delegating get_cache_info to style orchestrator.")
        return self._style_orchestrator.get_cache_info()

    # --- REMOVED METHODS (moved to StyleApplicationOrchestratorService) ---
    # _get_aci_color_map
    # _resolve_aci_color
    # _determine_entity_properties_from_style
    # _apply_text_entity_specifics
    # _apply_hatch_properties
    # _align_text_entity_to_view
