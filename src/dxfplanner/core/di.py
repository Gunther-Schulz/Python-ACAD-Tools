from dependency_injector import containers, providers
from typing import TYPE_CHECKING, Optional

# Configuration (Schema defined, loading is separate)
from dxfplanner.config.schemas import (
    DataSourceType, GeometryOperationType,
    ProjectConfig, # ADDED ProjectConfig for instance provider
    AttributeMappingServiceConfig, CoordinateServiceConfig, ValidationServiceConfig,
    DxfWriterConfig, # ADDED for DxfWriterConfig provider
    ShapefileSourceConfig, GeoJSONSourceConfig, CsvWktReaderConfig
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
    FilterByExtentOperation
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

# --- Module-level Resolver Implementations (MOVED HERE) ---
def _di_resolve_reader(container: 'DIContainerTypeHint', reader_type: DataSourceType) -> IGeoDataReader: # Ensure original signature
    # _di_debug_logger.critical(f"DI_DEBUG_LITE: _di_resolve_reader CALLED. container={type(container)}, reader_type={reader_type}") # REMOVE/COMMENT OUT

    # Original logic
    reader_provider = container._geo_data_readers_map_provider().get(reader_type)
    if not reader_provider:
        raise ConfigurationError(f"No reader configured for source type: {reader_type}")
    return reader_provider()

def _di_resolve_operation(container: 'DIContainerTypeHint', op_type: GeometryOperationType) -> IOperation:
    op_provider = container._operations_map_provider().get(op_type)
    if not op_provider:
        raise ConfigurationError(f"No operation configured for type: {op_type}")
    return op_provider()

class DIContainer(containers.DeclarativeContainer):
    """Dependency Injection Container for the DXFPlanner application."""

    # --- Configuration Provider ---
    # The actual AppConfig instance will be provided by the application's entry point
    # (e.g., main.py or app.py) after loading it from a file or environment.
    config = providers.Configuration(strict=True) # strict=True ensures all expected config is provided or has defaults
    logger = providers.Singleton(
        logging_config.get_logger
        # Assuming get_logger is sufficient. If setup_logging needs to be called with config:
        # providers.Factory(logging_config.setup_logging, config=config.logging) # if setup returns logger
        # For now, get_logger is simpler. Actual logging setup with config would be done
        # once at app startup by the main entry point, then get_logger retrieves it.
    )
    __self__ = providers.Self() # ADDED explicit self provider

    # --- Placeholder for the actual ProjectConfig instance ---
    # This will be overridden in app.py after the config is loaded.
    project_config_instance_provider = providers.Provider() # MODIFIED to be a generic Provider

    # --- Config Model Providers (defined first) ---
    attribute_mapping_service_config_provider = providers.Factory(
        AttributeMappingServiceConfig.model_validate,
        config.services.attribute_mapping
    )
    coordinate_service_config_provider = providers.Factory(
        CoordinateServiceConfig.model_validate,
        config.services.coordinate
    )
    validation_service_config_provider = providers.Factory(
        ValidationServiceConfig.model_validate,
        config.services.validation
    )
    shapefile_reader_config_provider = providers.Factory(
        ShapefileSourceConfig.model_validate,
        config.io.readers.shapefile
    )
    geojson_reader_config_provider = providers.Factory(
        GeoJSONSourceConfig.model_validate,
        config.io.readers.geojson
    )
    csv_wkt_reader_config_provider = providers.Factory(
        CsvWktReaderConfig.model_validate,
        config.io.readers.csv_wkt
    )
    dxf_writer_config_model_provider = providers.Factory(
        DxfWriterConfig.model_validate,
        config.dxf_writer
    )

    # --- I/O Readers (depend on their config model providers) ---
    shapefile_reader = providers.Factory(
        ShapefileReader,
        config=shapefile_reader_config_provider, # Direct name access
        logger=logger
    )
    geojson_reader = providers.Factory(
        GeoJsonReader,
        config=geojson_reader_config_provider, # Direct name access
        logger=logger
    )
    csv_wkt_reader = providers.Factory(
        CsvWktReader,
        config=csv_wkt_reader_config_provider, # Direct name access
        logger=logger
    )

    # --- GeoData Readers Map Provider (depends on individual readers) ---
    _geo_data_readers_map_provider = providers.Dict({
        DataSourceType.SHAPEFILE: shapefile_reader,
        DataSourceType.GEOJSON: geojson_reader,
        DataSourceType.CSV_WKT: csv_wkt_reader,
    })

    # --- Style Service (some operations/services depend on this) ---
    style_service = providers.Factory(
        StyleService,
        config=project_config_instance_provider,
        logger=logger
    )

    # --- Individual Operation Providers ---
    buffer_operation_provider = providers.Factory(BufferOperation, logger_param=logger)
    simplify_operation_provider = providers.Factory(SimplifyOperation)
    field_mapping_operation_provider = providers.Factory(FieldMappingOperation)
    reproject_operation_provider = providers.Factory(ReprojectOperation, logger_param=logger)
    clean_geometry_operation_provider = providers.Factory(CleanGeometryOperation, logger_param=logger)
    explode_multipart_operation_provider = providers.Factory(ExplodeMultipartOperation, logger_param=logger)
    merge_operation_provider = providers.Factory(MergeOperation, logger_param=logger)
    dissolve_operation_provider = providers.Factory(DissolveOperation, logger_param=logger)
    filter_by_attribute_operation_provider = providers.Factory(FilterByAttributeOperation, logger_param=logger)
    filter_by_extent_operation_provider = providers.Factory(FilterByExtentOperation, logger_param=logger)

    intersection_operation_provider = providers.Factory(
        IntersectionOperation,
        di_container=providers.Self,
        logger_param=logger
    )
    label_placement_service_provider = providers.Singleton(
        LabelPlacementService,
        logger_param=logger
    )
    label_placement_operation_provider = providers.Factory(
        LabelPlacementOperation,
        label_placement_service=label_placement_service_provider,
        style_service=style_service,
        logger_param=logger
    )

    # --- Operations Map Provider (depends on individual operations) ---
    _operations_map_provider = providers.Singleton(
        lambda buffer_op, simplify_op, field_map_op, reproj_op, clean_op, explode_op, intersect_op, merge_op, dissolve_op, filter_attr_op, label_place_op, filter_extent_op: {
            GeometryOperationType.BUFFER: buffer_op,
            GeometryOperationType.SIMPLIFY: simplify_op,
            GeometryOperationType.FIELD_MAPPING: field_map_op,
            GeometryOperationType.REPROJECT: reproj_op,
            GeometryOperationType.CLEAN_GEOMETRY: clean_op,
            GeometryOperationType.EXPLODE_MULTIPART: explode_op,
            GeometryOperationType.INTERSECTION: intersect_op,
            GeometryOperationType.MERGE: merge_op,
            GeometryOperationType.DISSOLVE: dissolve_op,
            GeometryOperationType.FILTER_BY_ATTRIBUTE: filter_attr_op,
            GeometryOperationType.LABEL_PLACEMENT: label_place_op,
            GeometryOperationType.FILTER_BY_EXTENT: filter_extent_op,
        },
        buffer_operation_provider,
        simplify_operation_provider,
        field_mapping_operation_provider,
        reproject_operation_provider,
        clean_geometry_operation_provider,
        explode_multipart_operation_provider,
        intersection_operation_provider,
        merge_operation_provider,
        dissolve_operation_provider,
        filter_by_attribute_operation_provider,
        label_placement_operation_provider,
        filter_by_extent_operation_provider
    )

    # --- Callable Providers for Resolvers (Using module-level functions) ---
    reader_resolver = providers.Callable(
        _di_resolve_reader,
        container=__self__  # CHANGED from providers.Self
    )
    operation_resolver = providers.Callable(
        _di_resolve_operation,
        container=__self__  # CHANGED from providers.Self
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
        reader_resolver_provider=reader_resolver, # CHANGED to direct name access from providers.Self.reader_resolver
        operation_resolver_provider=operation_resolver, # CHANGED to direct name access from providers.Self.operation_resolver
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
