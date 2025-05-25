"""Example test file demonstrating pytest marker usage."""
import pytest
import time


class TestMarkerExamples:
    """Example tests showing how to use the configured markers."""

    @pytest.mark.unit
    @pytest.mark.fast
    def test_fast_unit_example(self):
        """Example of a fast unit test."""
        assert 1 + 1 == 2

    @pytest.mark.unit
    @pytest.mark.domain
    def test_domain_unit_example(self):
        """Example of a domain model unit test."""
        # This would test domain models
        assert True

    @pytest.mark.integration
    @pytest.mark.services
    def test_service_integration_example(self):
        """Example of a service integration test."""
        # This would test service interactions
        assert True

    @pytest.mark.slow
    @pytest.mark.benchmark
    def test_slow_benchmark_example(self):
        """Example of a slow benchmark test."""
        time.sleep(0.1)  # Simulate slow operation
        assert True

    @pytest.mark.filesystem
    @pytest.mark.requires_test_data
    def test_filesystem_example(self):
        """Example of a test that requires filesystem access."""
        # This would test file operations
        assert True

    @pytest.mark.path_resolution
    @pytest.mark.unit
    def test_path_resolution_example(self):
        """Example of a path resolution test."""
        # This would test the hierarchical path alias system
        assert True

    @pytest.mark.config
    @pytest.mark.integration
    def test_config_integration_example(self):
        """Example of a configuration integration test."""
        # This would test configuration loading
        assert True

    @pytest.mark.dxf
    @pytest.mark.adapters
    def test_dxf_adapter_example(self):
        """Example of a DXF adapter test."""
        # This would test DXF file operations
        assert True

    @pytest.mark.cli
    @pytest.mark.e2e
    def test_cli_e2e_example(self):
        """Example of an end-to-end CLI test."""
        # This would test full CLI workflows
        assert True

    @pytest.mark.contract
    @pytest.mark.interfaces
    def test_interface_contract_example(self):
        """Example of an interface contract test."""
        # This would test Protocol implementations
        assert True

    @pytest.mark.skip_ci
    @pytest.mark.debug
    def test_debug_example(self):
        """Example of a debug test that should be skipped in CI."""
        # This would be for debugging specific issues
        assert True

    @pytest.mark.experimental
    def test_experimental_feature_example(self):
        """Example of a test for experimental features."""
        # This would test experimental functionality
        assert True


# Example of how to run specific marker combinations:
# pytest -m "unit and fast"                    # Run fast unit tests
# pytest -m "integration and not slow"         # Run integration tests that aren't slow
# pytest -m "domain or services"               # Run domain or service tests
# pytest -m "path_resolution"                  # Run all path resolution tests
# pytest -m "not (external or filesystem)"     # Run tests that don't need external resources
# pytest -m "unit and not skip_ci"             # Run unit tests suitable for CI
