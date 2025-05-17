from dependency_injector import containers, providers

# Configuration (Schema defined, loading is separate)
from dxfplanner.config.schemas import AppConfig, DataSourceType, OperationType # Added OperationType

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
from dxfplanner.services.geoprocessing.label_placement_service import LabelPlacementServiceImpl # Added
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
        config=config, # StyleService expects the full AppConfig
        logger=logger  # Added logger injection
    )

    # --- Geoprocessing Services (direct dependencies where needed) ---
    coordinate_service = providers.Factory(
        CoordinateTransformService,
        config=config.services.coordinate # CoordinateTransformService now takes its specific config
    )

    attribute_mapper_service = providers.Factory(
        AttributeMappingService,
        config=config.services.attribute_mapping, # AttributeMappingService now takes its specific config
        dxf_writer_config=config.io.writers.dxf, # ADDED
        logger_in=logger                         # ADDED
    )

    label_placement_service = providers.Factory(
        LabelPlacementServiceImpl,
        # app_config=config, # If it needs the full config
        # specific_config=config.services.label_placement, # If we add LabelPlacementServiceConfig to ServicesSettings
        logger=logger,
        style_service=style_service # Added style_service injection
        # Add other necessary dependencies for LabelPlacementServiceImpl if any are identified later
    )

    # --- Geometry Transformation Service ---
    # Note: IGeometryTransformer is an interface, GeometryTransformService is the implementation
    geometry_transformer_service = providers.Factory(
        GeometryTransformerImpl,
        attribute_mapper=attribute_mapper_service,
        style_service=style_service,  # ADDED style_service injection
        provides=IGeometryTransformer  # ADDED provides interface
    )

    # --- I/O Readers ---
    shapefile_reader = providers.Factory(
        ShapefileReader,
        config=config.io.readers.shapefile, # Pass specific config
        logger=logger                       # Pass logger
    )
    geojson_reader = providers.Factory(
        GeoJsonReader,
        config=config.io.readers.geojson, # Pass specific config
        logger=logger                      # Pass logger
    )
    # Add other readers here, e.g.:
    csv_wkt_reader = providers.Factory(
        CsvWktReader,
        config=config.io.readers.csv_wkt, # Pass specific config
        logger=logger                     # Pass logger
    )

    _geo_data_readers_map_provider = providers.Dict(
        {
            DataSourceType.SHAPEFILE: shapefile_reader,
            DataSourceType.GEOJSON: geojson_reader,
            DataSourceType.CSV_WKT: csv_wkt_reader, # Added CsvWktReader registration
        }
    )

    # --- Operation Providers ---
    # Most simple operations just take a logger now, or nothing.
    # Complex ones (Intersection, LabelPlacement) have specific dependencies.

    buffer_operation_provider = providers.Factory(
        BufferOperation,
        logger_param=logger # Added logger
    )
    simplify_operation_provider = providers.Factory(
        SimplifyOperation
        # logger_param=logger # Assuming no __init__ or logger if not specified
    )
    field_mapping_operation_provider = providers.Factory(
        FieldMappingOperation
        # logger_param=logger
    )
    reproject_operation_provider = providers.Factory(
        ReprojectOperation,
        logger_param=logger # Added logger
    )
    clean_geometry_operation_provider = providers.Factory(
        CleanGeometryOperation,
        logger_param=logger # Added logger
    )
    explode_multipart_operation_provider = providers.Factory(
        ExplodeMultipartOperation,
        logger_param=logger # Added logger
    )
    # IntersectionOperation already has its specific provider below
    merge_operation_provider = providers.Factory(
        MergeOperation,
        logger_param=logger # Added logger
    )
    dissolve_operation_provider = providers.Factory(
        DissolveOperation,
        logger_param=logger # Added logger
    )
    filter_by_attribute_operation_provider = providers.Factory(
        FilterByAttributeOperation,
        logger_param=logger # Added logger
    )
    # LabelPlacementOperation already has its specific provider below
    filter_by_extent_operation_provider = providers.Factory( # Added
        FilterByExtentOperation,
        logger_param=logger # Added logger
    )

    intersection_operation_provider = providers.Factory(
        IntersectionOperation,
        di_container=providers.Self, # Correctly injects the container itself
        logger_param=logger
    )

    label_placement_service_provider = providers.Singleton( # Referenced by LabelPlacementOperation
        LabelPlacementServiceImpl, # Changed from LabelPlacementService
        logger_param=logger
    )

    label_placement_operation_provider = providers.Factory(
        LabelPlacementOperation,
        label_placement_service=label_placement_service_provider,
        style_service=style_service_provider, # Corrected: Added _provider
        logger_param=logger
    )

    _operations_map_provider = providers.Singleton(
        lambda buffer_op, simplify_op, field_map_op, reproj_op, clean_op, explode_op, intersect_op, merge_op, dissolve_op, filter_attr_op, label_place_op, filter_extent_op: { # Added filter_extent_op
            OperationType.BUFFER: buffer_op,
            OperationType.SIMPLIFY: simplify_op,
            OperationType.FIELD_MAPPING: field_map_op,
            OperationType.REPROJECT: reproj_op,
            OperationType.CLEAN_GEOMETRY: clean_op,
            OperationType.EXPLODE_MULTIPART: explode_op,
            OperationType.INTERSECTION: intersect_op,
            OperationType.MERGE: merge_op,
            OperationType.DISSOLVE: dissolve_op,
            OperationType.FILTER_BY_ATTRIBUTE: filter_attr_op,
            OperationType.LABEL_PLACEMENT: label_place_op,
            OperationType.FILTER_BY_EXTENT: filter_extent_op, # Added
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
        filter_by_extent_operation_provider # Added
    )

    # --- DXF Writer Component Services (New) ---
    dxf_resource_setup_service = providers.Factory(
        DxfResourceSetupService,
        project_config=config, # Changed from app_config=config
        provides=IDxfResourceSetupService
    )

    dxf_entity_converter_service = providers.Factory(
        DxfEntityConverterService,
        project_config=config, # Changed from app_config=config
        provides=IDxfEntityConverterService
    )

    dxf_viewport_setup_service = providers.Factory(
        DxfViewportSetupService,
        project_config=config, # Changed from app_config=config
        provides=IDxfViewportSetupService
    )

    # --- I/O Writers (Original DxfWriter provider - to be updated later if it takes these services) ---
    dxf_writer = providers.Factory(
        DxfWriter,
        project_config=config, # Changed from app_config=config
        style_service=style_service,
        resource_setup_service=dxf_resource_setup_service, # ADDED
        entity_converter_service=dxf_entity_converter_service, # ADDED
        viewport_setup_service=dxf_viewport_setup_service, # ADDED
        legend_generator=legend_generation_service # ADDED and uncommented
    )

    # --- Higher Level Services ---
    layer_processor_service_provider = providers.Factory(
        LayerProcessorService,
        project_config=config, # Changed from app_config
        di_container=providers.Self,
        geometry_transformer=geometry_transformer_service,
        logger=logger
    )

    pipeline_service_provider = providers.Factory(
        PipelineService,
        project_config=config, # Changed from app_config
        layer_processor=layer_processor_service_provider,
        dxf_writer=dxf_writer,
        logger=logger
    )

    # --- Validation Service (Optional) ---
    validation_service = providers.Factory(
        ValidationService,
        config=config.services.validation # ValidationService now takes its specific config
    )

    # --- Main Orchestration Service (Top Level) ---
    dxf_generation_service = providers.Factory(
        DxfGenerationService,
        project_config=config, # Changed from app_config=config
        pipeline_service=pipeline_service_provider,
        validation_service=validation_service, # Optional
        provides=IDxfGenerationService
    )

    # --- Legend Generation Service (New) ---
    legend_generation_service_provider = providers.Factory(
        LegendGenerationService,
        project_config=config,
        logger=logger,
        dxf_writer=dxf_writer_provider, # Corrected: Added _provider
        style_service=style_service_provider, # Corrected: Added _provider
        entity_converter_service=dxf_entity_converter_service_provider # Corrected: Added _provider
    )

    # --- Resolver methods (part of the container's public API if needed elsewhere) ---
    def resolve_reader(self, reader_type: DataSourceType) -> IGeoDataReader:
        reader_provider = self._geo_data_readers_map_provider().get(reader_type)
        if not reader_provider:
            raise ConfigurationError(f"No reader configured for source type: {reader_type.value}")
        return reader_provider()

    def resolve_operation(self, op_type: OperationType) -> IOperation:
        operation_provider = self._operations_map_provider().get(op_type)
        if not operation_provider:
            self.logger().error(f"Attempted to resolve an unknown or unconfigured operation type: {op_type.value}")
            raise ConfigurationError(f"Operation type '{op_type.value}' is not recognized or no provider is registered for it in the DI container.")
        return operation_provider()

# Global container instance, to be initialized by the application entry point
# Example:
# container = Container()
# app_config_instance = load_config_from_yaml() # From dxfplanner.config.loaders
# container.config.from_pydantic(app_config_instance)
# container.wire(modules=[__name__, ".app", ".cli", "dxfplanner.services.orchestration_service", ...]) # etc.
# Now services can import `container` and access dependencies.
# Or, the entry point can retrieve top-level services from the container and run them.
