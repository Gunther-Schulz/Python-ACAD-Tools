from dependency_injector import containers, providers

# Configuration (Schema defined, loading is separate)
from dxfplanner.config.schemas import AppConfig, DataSourceType # Added DataSourceType

# Core components
from dxfplanner.core import logging_config
from dxfplanner.core.exceptions import DXFPlannerBaseError # Not directly injected, but good to be aware

# Domain Interfaces (for type hinting and clarity if needed, though providers handle types)
from dxfplanner.domain.interfaces import (
    IGeoDataReader, IDxfWriter, IGeometryTransformer,
    ICoordinateService, IAttributeMapper, IValidationService,
    IDxfGenerationService
)

# Service Implementations
from dxfplanner.services.geoprocessing.coordinate_service import CoordinateTransformService
from dxfplanner.services.geoprocessing.attribute_mapping_service import AttributeMappingService
from dxfplanner.geometry.transformations import GeometryTransformerImpl
from dxfplanner.services.validation_service import ValidationService
from dxfplanner.services.orchestration_service import DxfGenerationService
from dxfplanner.services.style_service import StyleService
from dxfplanner.services.operation_service import OperationService

# I/O Implementations
from dxfplanner.io.readers.shapefile_reader import ShapefileReader
from dxfplanner.io.readers.geojson_reader import GeoJsonReader # Added GeoJsonReader
# from dxfplanner.io.readers.csv_wkt_reader import CsvWktReader # Placeholder for future
from dxfplanner.io.writers.dxf_writer import DxfWriter


class Container(containers.DeclarativeContainer):
    """Dependency Injection Container for the DXFPlanner application."""

    # --- Configuration Provider ---
    # The actual AppConfig instance will be provided by the application's entry point
    # (e.g., main.py or app.py) after loading it from a file or environment.
    config = providers.Configuration(strict=True) # strict=True ensures all expected config is provided or has defaults

    # --- Core Services ---
    logger = providers.Singleton(
        logging_config.get_logger
        # Assuming get_logger is sufficient. If setup_logging needs to be called with config:
        # providers.Factory(logging_config.setup_logging, config=config.logging) # if setup returns logger
        # For now, get_logger is simpler. Actual logging setup with config would be done
        # once at app startup by the main entry point, then get_logger retrieves it.
    )

    # --- Style Service ---
    style_service = providers.Factory(
        StyleService,
        config=config # StyleService expects the full AppConfig
    )

    # --- Operation Service ---
    operation_service = providers.Factory(
        OperationService,
        app_config=config # OperationService expects the full AppConfig
    )

    # --- Geoprocessing Services ---
    coordinate_service = providers.Factory(
        CoordinateTransformService,
        # config=config.services.coordinate # If CoordinateTransformService takes its own sub-config
    )

    attribute_mapper_service = providers.Factory(
        AttributeMappingService,
        # config=config.services.attribute_mapping # If AttributeMappingService takes its own sub-config
    )

    # --- Geometry Transformation Service ---
    # Note: IGeometryTransformer is an interface, GeometryTransformService is the implementation
    geometry_transformer_service = providers.Factory(
        GeometryTransformerImpl,
        attribute_mapper=attribute_mapper_service,
        # config=config.services.geometry_transform # If it takes its own sub-config
    )

    # --- I/O Readers ---
    shapefile_reader = providers.Factory(
        ShapefileReader,
        app_config=config # ShapefileReader now takes app_config
    )
    geojson_reader = providers.Factory(
        GeoJsonReader,
        app_config=config # GeoJsonReader also takes app_config
    )
    # Add other readers here, e.g.:
    # csv_wkt_reader = providers.Factory(CsvWktReader, app_config=config)

    geo_data_readers_map = providers.Dict(
        {
            DataSourceType.SHAPEFILE: shapefile_reader,
            DataSourceType.GEOJSON: geojson_reader,
            # DataSourceType.CSV_WKT: csv_wkt_reader, # When CsvWktReader is ready
        }
    )

    # --- I/O Writers ---
    dxf_writer = providers.Factory(
        DxfWriter,
        app_config=config, # DxfWriter now takes the full AppConfig
        style_service=style_service
    )

    # --- Validation Service ---
    validation_service = providers.Factory(
        ValidationService,
        # config=config.services.validation # If ValidationService takes its own sub-config
    )

    # --- Main Orchestration Service ---
    dxf_generation_service = providers.Factory(
        DxfGenerationService,
        app_config=config, # DxfGenerationService now takes the full AppConfig
        geo_data_readers=geo_data_readers_map, # Updated to use the map
        geometry_transformer=geometry_transformer_service,
        dxf_writer=dxf_writer,
        style_service=style_service, # DxfGenerationService was already taking this
        operation_service=operation_service, # Added
        validation_service=validation_service,
        # config=config.services.dxf_generation # If it takes its own sub-config
    )

# Global container instance, to be initialized by the application entry point
# Example:
# container = Container()
# app_config_instance = load_config_from_yaml() # From dxfplanner.config.loaders
# container.config.from_pydantic(app_config_instance)
# container.wire(modules=[__name__, ".app", ".cli", "dxfplanner.services.orchestration_service", ...]) # etc.
# Now services can import `container` and access dependencies.
# Or, the entry point can retrieve top-level services from the container and run them.
