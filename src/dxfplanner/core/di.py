from dependency_injector import containers, providers
from typing import TYPE_CHECKING, Optional
import logging # Ensure logging is imported

# Configuration (Schema defined, loading is separate)
from dxfplanner.config.schemas import (
    DataSourceType, GeometryOperationType,
    ProjectConfig, # ADDED ProjectConfig for instance provider
    AttributeMappingServiceConfig, CoordinateServiceConfig, ValidationServiceConfig,
    DxfWriterConfig, # ADDED for DxfWriterConfig provider
    ShapefileSourceConfig, GeoJSONSourceConfig, CsvWktReaderConfig,
    AnyOperationConfig # ADDED for op_config
)

# Core components
from dxfplanner.core import logging_config
from dxfplanner.core.exceptions import DXFPlannerBaseError, ConfigurationError # Not directly injected, but good to be aware

# Domain Interfaces (for type hinting and clarity if needed, though providers handle types)
from dxfplanner.domain.interfaces import (
    IGeoDataReader, IDxfWriter, IGeometryTransformer,
    ICoordinateService, IAttributeMapper, IValidationService,
    IDxfGenerationService, IOperation, ILegendGenerator, IStyleService, # Added IStyleService
    ILabelPlacementService, IPipelineService, ILayerProcessorService,
    IDxfResourceSetupService, IDxfEntityConverterService, IDxfViewportSetupService
)

# Service Implementations
from dxfplanner.services.geoprocessing.coordinate_service import CoordinateTransformService
from dxfplanner.services.geoprocessing.attribute_mapping_service import AttributeMappingService
from dxfplanner.services.geoprocessing.label_placement_service import LabelPlacementService
from dxfplanner.geometry.transformations import GeometryTransformerImpl
from dxfplanner.services.validation_service import ValidationService
from dxfplanner.services.orchestration_service import DxfGenerationService
from dxfplanner.services.style_service import StyleService
from dxfplanner.services.layer_processor_service import LayerProcessorService # New
from dxfplanner.services.pipeline_service import PipelineService # New
from dxfplanner.services.legend_generation_service import LegendGenerationService # New

# I/O Implementations
from dxfplanner.io.readers.shapefile_reader import ShapefileReader
from dxfplanner.io.readers.geojson_reader import GeoJsonReader # Added GeoJsonReader
from dxfplanner.io.readers.csv_wkt_reader import CsvWktReader # Added
from dxfplanner.io.writers.dxf_writer import DxfWriter

# Operation Implementations
from dxfplanner.geometry.operations import (
    BufferOperation, SimplifyOperation, FieldMappingOperation,
    ReprojectOperation, CleanGeometryOperation, ExplodeMultipartOperation,
    IntersectionOperation,
    MergeOperation,
    DissolveOperation,
    FilterByAttributeOperation,
    LabelPlacementOperation,
    FilterByExtentOperation,
)

# ADD NEW DXF WRITER COMPONENT SERVICE IMPLEMENTATIONS
from dxfplanner.io.writers.components.dxf_resource_setup_service import DxfResourceSetupService
from dxfplanner.io.writers.components.dxf_entity_converter_service import DxfEntityConverterService
from dxfplanner.io.writers.components.dxf_viewport_setup_service import DxfViewportSetupService

from typing import TYPE_CHECKING # For forward reference of DIContainer in module functions
if TYPE_CHECKING:
    from dxfplanner.core.di import DIContainer as DIContainerTypeHint # Alias for type hint

# --- START ADDED DEBUG LOGGING ---
# import logging # Keep if other loggers use it, or remove if exclusive to di_debug_logger
# _di_debug_logger = logging.getLogger(f"{__name__}.di_debug") # REMOVE/COMMENT OUT
# --- END ADDED DEBUG LOGGING ---

# --- Module-level Resolver Implementations ---
# REMOVE def _di_resolve_operation(...) function entirely

class DIContainer(containers.DeclarativeContainer):
    """Dependency Injection Container for the DXFPlanner application."""

    __self__ = providers.Self()

    # Configuration provider
    config = providers.Configuration()

    # Placeholder for the actual ProjectConfig Pydantic model instance
    # This will be overridden in app.py after the config is loaded.
    project_config_instance_provider = providers.Provider[ProjectConfig]() # Generic provider, can add type hint

    # Logger Provider (depends on config values loaded into 'config')
    logger = providers.Singleton(
        logging.getLogger,
        # name will be resolved from container.config after it's loaded in app.py
        name=config.logging.default_logger_name
    )

    # --- Config Model Providers (these take a dict/kwargs, not the full ProjectConfig instance directly) ---
    # These are for specific sub-sections of the config, still useful.
    # They will use container.config.services.attribute_mapping() etc.
    attribute_mapping_service_config_provider = providers.Factory(
        AttributeMappingServiceConfig.model_validate,
        config.services.attribute_mapping # This now refers to the config provider
    )
    coordinate_service_config_provider = providers.Factory(
        CoordinateServiceConfig.model_validate,
        config.services.coordinate
    )
    validation_service_config_provider = providers.Factory(
        ValidationServiceConfig.model_validate,
        config.services.validation
    )
    dxf_writer_config_model_provider = providers.Factory(
        DxfWriterConfig.model_validate,
        config.dxf_writer
    )

    # --- I/O Readers (depend on their config model providers) ---
    shapefile_reader_provider = providers.Factory(ShapefileReader)
    geojson_reader_provider = providers.Factory(GeoJsonReader)
    csv_wkt_reader_provider = providers.Factory(CsvWktReader)

    # --- GeoData Readers Map ---
    # This is now a direct Python dictionary holding the factory providers.
    # It's not a dependency_injector provider itself, but its contents are.
    # LayerProcessorService will be injected with this dictionary.
    _geo_data_reader_factories_map = {
        DataSourceType.SHAPEFILE: shapefile_reader_provider,
        DataSourceType.GEOJSON: geojson_reader_provider,
        DataSourceType.CSV_WKT: csv_wkt_reader_provider,
    }

    # --- Style Service (some operations/services depend on this) ---
    style_service = providers.Factory(
        StyleService,
        config=project_config_instance_provider,
        logger=logger
    )

    # --- Individual Operation Providers ---
    buffer_operation_provider = providers.Factory(BufferOperation)
    simplify_operation_provider = providers.Factory(SimplifyOperation)
    field_mapping_operation_provider = providers.Factory(FieldMappingOperation)
    reproject_operation_provider = providers.Factory(ReprojectOperation)
    clean_geometry_operation_provider = providers.Factory(CleanGeometryOperation)
    explode_multipart_operation_provider = providers.Factory(ExplodeMultipartOperation)
    merge_operation_provider = providers.Factory(MergeOperation)
    dissolve_operation_provider = providers.Factory(DissolveOperation)
    filter_by_attribute_operation_provider = providers.Factory(FilterByAttributeOperation, logger_param=logger)
    filter_by_extent_operation_provider = providers.Factory(FilterByExtentOperation, logger_param=logger)

    intersection_operation_provider = providers.Factory(
        IntersectionOperation,
        di_container=__self__
    )
    label_placement_service_provider = providers.Singleton(
        LabelPlacementService,
        logger=logger
    )
    label_placement_operation_provider = providers.Factory(
        LabelPlacementOperation,
        label_placement_service=label_placement_service_provider,
        style_service=style_service,
        logger_param=logger
    )

    # --- Operations Map (Direct Python Dictionary) ---
    _OPERATIONS_FACTORIES_STATIC_MAP = { # Renamed from _operations_map
        GeometryOperationType.BUFFER: buffer_operation_provider,
        GeometryOperationType.INTERSECTION: intersection_operation_provider,
        GeometryOperationType.LABEL_PLACEMENT: label_placement_operation_provider,
        GeometryOperationType.REPROJECT: reproject_operation_provider,
        GeometryOperationType.SIMPLIFY: simplify_operation_provider,
        GeometryOperationType.FIELD_MAPPING: field_mapping_operation_provider,
        GeometryOperationType.CLEAN_GEOMETRY: clean_geometry_operation_provider,
        GeometryOperationType.EXPLODE_MULTIPART: explode_multipart_operation_provider,
        GeometryOperationType.MERGE: merge_operation_provider,
        GeometryOperationType.DISSOLVE: dissolve_operation_provider,
        GeometryOperationType.FILTER_BY_ATTRIBUTE: filter_by_attribute_operation_provider,
        GeometryOperationType.FILTER_BY_EXTENT: filter_by_extent_operation_provider,
    }

    operations_map_provider = providers.Dict(
        _OPERATIONS_FACTORIES_STATIC_MAP
    )

    # --- Core Geoprocessing Services (defined after their dependencies like style_service) ---
    coordinate_service = providers.Factory(
        CoordinateTransformService,
        config=coordinate_service_config_provider
    )
    attribute_mapper_service = providers.Factory(
        AttributeMappingService,
        config=attribute_mapping_service_config_provider,
        dxf_writer_config=dxf_writer_config_model_provider,
        logger_in=logger
    )
    geometry_transformer_service = providers.Factory(
        GeometryTransformerImpl,
        style_service=style_service
    )

    # --- Higher Level Services (defined after their dependencies) ---\n    # LayerProcessorService depends on reader_resolver, operation_resolver, and geometry_transformer_service
    layer_processor_service_provider = providers.Factory(
        LayerProcessorService,
        project_config=project_config_instance_provider,
        geo_data_reader_factories_map=_geo_data_reader_factories_map,
        operations_map=operations_map_provider,
        geometry_transformer=geometry_transformer_service,
        logger=logger
    )

    dxf_resource_setup_service = providers.Factory(
        DxfResourceSetupService,
        project_config=project_config_instance_provider
    )
    dxf_entity_converter_service = providers.Factory(
        DxfEntityConverterService,
        project_config=project_config_instance_provider # Assuming it takes ProjectConfig
    )
    dxf_viewport_setup_service = providers.Factory(
        DxfViewportSetupService,
        project_config=project_config_instance_provider
    )
    legend_generation_service_provider = providers.Factory(
        LegendGenerationService,
        config=project_config_instance_provider,
        logger=logger,
        style_service=style_service,
        entity_converter_service=dxf_entity_converter_service
    )
    dxf_writer = providers.Factory(
        DxfWriter,
        project_config=project_config_instance_provider,
        style_service=style_service,
        resource_setup_service=dxf_resource_setup_service,
        entity_converter_service=dxf_entity_converter_service,
        viewport_setup_service=dxf_viewport_setup_service,
        legend_generator=legend_generation_service_provider
    )
    pipeline_service_provider = providers.Factory(
        PipelineService,
        project_config=project_config_instance_provider,
        layer_processor=layer_processor_service_provider,
        dxf_writer=dxf_writer,
        logger=logger
    )
    validation_service = providers.Factory(
        ValidationService,
        config=validation_service_config_provider
    )
    # --- Main Orchestration Service (Top Level) ---
    dxf_generation_service = providers.Factory(
        DxfGenerationService,
        project_config=project_config_instance_provider,
        pipeline_service=pipeline_service_provider,
        validation_service=validation_service,
    )

# Global container instance, to be initialized by the application entry point
# Example:
# container = DIContainer()
# app_config_instance = load_config_from_yaml() # From dxfplanner.config.loaders
# container.config.from_pydantic(app_config_instance)
# container.wire(modules=[__name__, ".app", ".cli", "dxfplanner.services.orchestration_service", ...]) # etc.
# Now services can import `container` and access dependencies.
# Or, the entry point can retrieve top-level services from the container and run them.
