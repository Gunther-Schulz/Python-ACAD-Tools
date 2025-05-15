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
    ILabelPlacementService # Added
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
    LabelPlacementOperation
)


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

    # --- Operation Implementations ---
    buffer_operation = providers.Factory(BufferOperation) # Operations are parameterless for now
    simplify_operation = providers.Factory(SimplifyOperation)
    field_mapping_operation = providers.Factory(FieldMappingOperation)
    reproject_operation = providers.Factory(ReprojectOperation)
    clean_geometry_operation = providers.Factory(CleanGeometryOperation)
    explode_multipart_operation = providers.Factory(ExplodeMultipartOperation)
    intersection_operation = providers.Factory( # Added IntersectionOperation
        IntersectionOperation,
        di_container=providers.Self # IntersectionOperation requires the container
    )
    # ADDED PLACEHOLDER FACTORIES:
    merge_operation = providers.Factory(MergeOperation)
    dissolve_operation = providers.Factory(DissolveOperation)
    filter_by_attribute_operation = providers.Factory(FilterByAttributeOperation)
    # ADDED LABEL PLACEMENT FACTORY:

    # ... other operations
    _operations_map_provider = providers.Dict(
        {
            OperationType.BUFFER: buffer_operation,
            OperationType.SIMPLIFY: simplify_operation,
            OperationType.FIELD_MAPPER: field_mapping_operation,
            OperationType.REPROJECT: reproject_operation,
            OperationType.CLEAN_GEOMETRY: clean_geometry_operation,
            OperationType.EXPLODE_MULTIPART: explode_multipart_operation,
            OperationType.INTERSECTION: intersection_operation, # Added
            # ADDED PLACEHOLDER REGISTRATIONS:
            OperationType.MERGE: merge_operation,
            OperationType.DISSOLVE: dissolve_operation,
            OperationType.FILTER_BY_ATTRIBUTE: filter_by_attribute_operation,
            # ADDED LABEL PLACEMENT REGISTRATION:
            OperationType.LABEL_PLACEMENT: providers.Factory(
                LabelPlacementOperation,
                label_placement_service=label_placement_service,
                style_service=style_service
            ),
        }
    )

    # --- I/O Writers ---
    dxf_writer = providers.Factory(
        DxfWriter,
        app_config=config, # DxfWriter now takes the full AppConfig
        style_service=style_service
    )

    # --- Higher Level Services ---
    layer_processor_service = providers.Factory(
        LayerProcessorService,
        app_config=config,
        di_container=providers.Self, # Pass the container itself for resolving readers/ops
        geometry_transformer=geometry_transformer_service,
        logger=logger # Added logger injection
    )
    pipeline_service = providers.Factory(
        PipelineService,
        app_config=config,
        layer_processor=layer_processor_service,
        dxf_writer=dxf_writer
    )

    # --- Validation Service (Optional) ---
    validation_service = providers.Factory(
        ValidationService,
        config=config.services.validation # ValidationService now takes its specific config
    )

    # --- Main Orchestration Service (Top Level) ---
    dxf_generation_service = providers.Factory(
        DxfGenerationService,
        app_config=config,
        pipeline_service=pipeline_service, # Main dependency changed
        validation_service=validation_service # Optional
    )

    # --- Legend Generation Service (New) ---
    legend_generation_service = providers.Factory(
        LegendGenerationService,
        config=config,
        logger=logger,
        dxf_writer=dxf_writer,
        style_service=style_service, # Added style_service injection
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
            raise ConfigurationError(f"No operation implementation configured for type: {op_type.value}")
        return operation_provider()

# Global container instance, to be initialized by the application entry point
# Example:
# container = Container()
# app_config_instance = load_config_from_yaml() # From dxfplanner.config.loaders
# container.config.from_pydantic(app_config_instance)
# container.wire(modules=[__name__, ".app", ".cli", "dxfplanner.services.orchestration_service", ...]) # etc.
# Now services can import `container` and access dependencies.
# Or, the entry point can retrieve top-level services from the container and run them.
