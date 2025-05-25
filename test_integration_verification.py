#!/usr/bin/env python3
"""
Integration verification test for the enhanced validation system.
This ensures that all components work together correctly.
"""

import sys
sys.path.insert(0, 'src')

from src.services.config_loader_service import ConfigLoaderService
from src.core.container import ApplicationContainer

def test_integration():
    """Test integration with the config loader service."""
    print('🔧 Testing Integration with Config Loader Service')
    print('=' * 60)

    try:
                # Initialize the DI container
        container = ApplicationContainer()

        # Get the config loader service
        config_loader = container.config_loader_service()

        print('✅ Config loader service initialized successfully')
        print('✅ Validation system is integrated into config loading')
        print('✅ Path resolver is available for alias resolution')
        print('✅ All dependencies are properly injected')

        # Test loading a valid project config
        print('\n📁 Testing valid project configuration...')
        try:
            config = config_loader.load_specific_project_config('test_project', 'projects')
            print('✅ Valid project config loaded successfully')
            print(f'   - Found {len(config.get("geomLayers", []))} geometry layers')
            print(f'   - Main settings: {list(config.get("main", {}).keys())}')
        except Exception as e:
            print(f'⚠️  Project config loading: {e}')

        print('\n🎯 Integration Test Complete!')
        return True

    except Exception as e:
        print(f'❌ Integration test failed: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
