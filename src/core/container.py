"""Dependency Injection Container for the application following PROJECT_ARCHITECTURE.MD."""
from dependency_injector import containers, providers
from dependency_injector.providers import Factory, Singleton

from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.config_loader_interface import IConfigLoader
from ..interfaces.data_source_interface import IDataSource
from ..interfaces.data_exporter_interface import IDataExporter
from ..interfaces.style_applicator_interface import IStyleApplicator
from ..interfaces.resource_manager_interface import IResourceManager
from ..interfaces.config_validation_interface import IConfigValidation
from ..interfaces.operation_registry_interface import IOperationRegistry
from ..interfaces.dxf_adapter_interface import IDXFAdapter
from ..interfaces.path_resolver_interface import IPathResolver

from ..services.logging_service import LoggingService
from ..services.config_loader_service import ConfigLoaderService
from ..services.data_source_service import DataSourceService
from ..services.data_exporter_service import DataExporterService
from ..services.style_applicator_service import StyleApplicatorService
from ..services.resource_manager_service import ResourceManagerService
from ..services.project_orchestrator_service import ProjectOrchestratorService
from ..services.geometry_processor_service import GeometryProcessorService
from ..services.path_resolver_service import PathResolverService
from ..domain.config_validation import ConfigValidationService
from ..services.operations.operation_registry import OperationRegistry
from ..adapters.ezdxf_adapter import EzdxfAdapter
from ..core.factories import ServiceFactory, HandlerFactory, FactoryRegistry

from ..domain.config_models import AppConfig


class ApplicationContainer(containers.DeclarativeContainer):
    """Main DI container for the application."""

    # Configuration
    config = providers.Configuration()

    # Core services (singletons)
    logging_service = Singleton(
        LoggingService,
        log_level_console=config.log_level_console,
        log_level_file=config.log_level_file,
        log_file_path=config.log_file_path
    )

    app_config = Singleton(
        AppConfig
    )

    config_validation_service = Singleton(
        ConfigValidationService
    )

    # Path resolution service (must be before config_loader_service)
    path_resolver_service = Singleton(
        PathResolverService,
        logger_service=logging_service
    )

    config_loader_service = Singleton(
        ConfigLoaderService,
        logger_service=logging_service,
        app_config=app_config,
        path_resolver=path_resolver_service
    )

    resource_manager_service = Singleton(
        ResourceManagerService,
        logger_service=logging_service
    )

    # Factories and Registries
    service_factory = Singleton(
        ServiceFactory,
        logger_service=logging_service
    )

    handler_factory = Singleton(
        HandlerFactory,
        logger_service=logging_service
    )

    factory_registry = Singleton(
        FactoryRegistry,
        logger_service=logging_service
    )

    # Adapters
    dxf_adapter = Singleton(
        EzdxfAdapter,
        logger_service=logging_service
    )

    # Data services
    data_source_service = Singleton(
        DataSourceService,
        logger_service=logging_service
    )

    data_exporter_service = Singleton(
        DataExporterService,
        logger_service=logging_service
    )

    style_applicator_service = Singleton(
        StyleApplicatorService,
        config_loader=config_loader_service,
        logger_service=logging_service
    )

    operation_registry = Singleton(
        OperationRegistry,
        logger_service=logging_service,
        data_source_service=data_source_service
    )

    # Processing services
    geometry_processor_service = Singleton(
        GeometryProcessorService,
        logger_service=logging_service,
        data_source_service=data_source_service,
        path_resolver_service=path_resolver_service
    )

    project_orchestrator_service = Singleton(
        ProjectOrchestratorService,
        logging_service=logging_service,
        config_loader=config_loader_service,
        data_source=data_source_service,
        geometry_processor=geometry_processor_service,
        style_applicator=style_applicator_service,
        data_exporter=data_exporter_service,
        path_resolver=path_resolver_service
    )
