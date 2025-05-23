"""Dependency injection container configuration."""
from dependency_injector import containers, providers

from ..services.logging_service import LoggingService
from ..services.config_loader_service import ConfigLoaderService
from ..services.data_source_service import DataSourceService
from ..services.geometry_processor_service import GeometryProcessorService
from ..services.style_applicator_service import StyleApplicatorService
from ..services.data_exporter_service import DataExporterService
from ..services.project_orchestrator_service import ProjectOrchestratorService
from ..services.resource_manager_service import ResourceManagerService
from ..services.operations.operation_registry import OperationRegistry
from ..adapters.ezdxf_adapter import EzdxfAdapter
from ..domain.config_validation import ConfigValidationService
from .factories import ServiceFactory, HandlerFactory, FactoryRegistry
from ..domain.config_models import AppConfig


class ApplicationContainer(containers.DeclarativeContainer):
    """Main dependency injection container for the application."""

    # Configuration
    config = providers.Configuration()

    # Core Services
    logging_service = providers.Singleton(
        LoggingService
    )

    resource_manager = providers.Singleton(
        ResourceManagerService,
        logger_service=logging_service
    )

    # Factories and Registries
    service_factory = providers.Singleton(
        ServiceFactory,
        logger_service=logging_service
    )

    handler_factory = providers.Singleton(
        HandlerFactory,
        logger_service=logging_service
    )

    factory_registry = providers.Singleton(
        FactoryRegistry,
        logger_service=logging_service
    )

    # Validation Services
    config_validation = providers.Singleton(
        ConfigValidationService
    )

    # Adapters
    dxf_adapter = providers.Singleton(
        EzdxfAdapter,
        logger_service=logging_service
    )

    config_loader = providers.Singleton(
        ConfigLoaderService,
        logger_service=logging_service,
        app_config=config.app_config
    )

    data_source = providers.Singleton(
        DataSourceService,
        logger_service=logging_service
    )

    # Operation Registry
    operation_registry = providers.Singleton(
        OperationRegistry,
        logger_service=logging_service,
        data_source_service=data_source
    )

    geometry_processor = providers.Singleton(
        GeometryProcessorService,
        logger_service=logging_service,
        data_source_service=data_source
    )

    style_applicator = providers.Singleton(
        StyleApplicatorService,
        config_loader=config_loader,
        logger_service=logging_service
    )

    data_exporter = providers.Singleton(
        DataExporterService,
        logger_service=logging_service
    )

    project_orchestrator = providers.Factory(
        ProjectOrchestratorService,
        logging_service=logging_service,
        config_loader=config_loader,
        data_source=data_source,
        geometry_processor=geometry_processor,
        style_applicator=style_applicator,
        data_exporter=data_exporter
    )
