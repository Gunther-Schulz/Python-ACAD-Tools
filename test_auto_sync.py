#!/usr/bin/env python3
"""
Integration test for hash-based auto sync system.
Tests the complete workflow from YAML configuration to DXF sync and back.
"""

import os
import sys
import json
import tempfile
import shutil
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, 'src')

from sync_hash_utils import (
    calculate_entity_content_hash,
    initialize_sync_metadata_if_missing,
    validate_and_repair_sync_metadata,
    ensure_sync_metadata_complete,
    detect_entity_changes,
    clean_entity_config_for_yaml_output
)
from viewport_manager import ViewportManager
from text_insert_manager import TextInsertManager


def test_hash_calculation():
    """Test that hash calculation is consistent and deterministic."""
    print("Testing hash calculation...")

    # Test viewport hash
    viewport_config = {
        'name': 'Test_Viewport',
        'center': {'x': 100.0, 'y': 200.0},
        'width': 300.0,
        'height': 150.0,
        'scale': 2.0
    }

    hash1 = calculate_entity_content_hash(viewport_config, 'viewport')
    hash2 = calculate_entity_content_hash(viewport_config, 'viewport')

    assert hash1 == hash2, "Hash calculation should be deterministic"
    assert len(hash1) == 64, "Hash should be 64 characters (SHA-256)"
    print(f"✓ Viewport hash: {hash1[:12]}...")

    # Test that different content produces different hash
    viewport_config_modified = viewport_config.copy()
    viewport_config_modified['scale'] = 1.5
    hash3 = calculate_entity_content_hash(viewport_config_modified, 'viewport')

    assert hash1 != hash3, "Different content should produce different hash"
    print(f"✓ Modified viewport hash: {hash3[:12]}... (different)")

    # Test text hash
    text_config = {
        'name': 'Test_Text',
        'text': 'Hello World',
        'position': {'type': 'absolute', 'x': 50.0, 'y': 800.0}
    }

    text_hash = calculate_entity_content_hash(text_config, 'text')
    assert len(text_hash) == 64, "Text hash should also be 64 characters"
    print(f"✓ Text hash: {text_hash[:12]}...")

    print("Hash calculation tests passed!\n")


def test_metadata_initialization():
    """Test sync metadata initialization for auto sync entities."""
    print("Testing metadata initialization...")

    # Test entity without sync metadata
    entity_config = {
        'name': 'Test_Entity',
        'center': {'x': 100, 'y': 200},
        'sync': 'auto'
    }

    # Should initialize metadata
    result = initialize_sync_metadata_if_missing(entity_config, 'viewport')
    assert result == True, "Should initialize missing metadata"
    assert '_sync' in entity_config, "Should add _sync section"
    assert 'content_hash' in entity_config['_sync'], "Should add content hash"
    print(f"✓ Initialized metadata: {entity_config['_sync']['content_hash'][:12]}...")

    # Should not re-initialize if already present
    result2 = initialize_sync_metadata_if_missing(entity_config, 'viewport')
    assert result2 == False, "Should not re-initialize existing metadata"
    print("✓ Did not re-initialize existing metadata")

    print("Metadata initialization tests passed!\n")


def test_change_detection():
    """Test change detection logic."""
    print("Testing change detection...")

    # Mock entity manager
    mock_manager = Mock()
    mock_manager._extract_dxf_entity_properties_for_hash.return_value = {
        'name': 'Test_Entity',
        'center': {'x': 100, 'y': 200},
        'width': 300,
        'height': 150
    }

    # Test no changes
    yaml_config = {
        'name': 'Test_Entity',
        'center': {'x': 100, 'y': 200},
        'width': 300,
        'height': 150,
        '_sync': {
            'content_hash': calculate_entity_content_hash({
                'name': 'Test_Entity',
                'center': {'x': 100, 'y': 200},
                'width': 300,
                'height': 150
            }, 'viewport')
        }
    }

    mock_dxf_entity = Mock()
    changes = detect_entity_changes(yaml_config, mock_dxf_entity, 'viewport', mock_manager)

    print(f"Change detection result: {changes}")
    assert not changes['yaml_changed'], "YAML should not show as changed"
    assert not changes['dxf_changed'], "DXF should not show as changed"
    assert not changes['has_conflict'], "Should not have conflict"
    print("✓ Correctly detected no changes")

    # Test YAML changed
    yaml_config_modified = yaml_config.copy()
    yaml_config_modified['width'] = 400  # Change width

    changes = detect_entity_changes(yaml_config_modified, mock_dxf_entity, 'viewport', mock_manager)
    assert changes['yaml_changed'], "Should detect YAML change"
    assert not changes['dxf_changed'], "DXF should not show as changed"
    print("✓ Correctly detected YAML change")

    print("Change detection tests passed!\n")


def test_yaml_cleaning():
    """Test YAML output cleaning function."""
    print("Testing YAML cleaning...")

    # Test entity with sync metadata
    entity_config = {
        'name': 'Test_Entity',
        'center': {'x': 100, 'y': 200},
        '_sync': {
            'content_hash': 'abc123def456',
            'last_sync_time': 1703123456,
            'sync_source': 'yaml',
            'conflict_policy': None  # Should be removed
        }
    }

    cleaned = clean_entity_config_for_yaml_output(entity_config)

    assert '_sync' in cleaned, "Should preserve sync metadata"
    assert 'conflict_policy' not in cleaned['_sync'], "Should remove null values"
    assert cleaned['_sync']['last_sync_time'] == 1703123456, "Should preserve valid values"
    print("✓ Correctly cleaned YAML output")

    # Test entity without sync metadata
    simple_config = {
        'name': 'Simple_Entity',
        'text': 'Hello'
    }

    cleaned_simple = clean_entity_config_for_yaml_output(simple_config)
    assert '_sync' not in cleaned_simple, "Should not add empty sync metadata"
    print("✓ Did not add unnecessary sync metadata")

    print("YAML cleaning tests passed!\n")


def test_batch_metadata_operations():
    """Test batch operations for multiple entities."""
    print("Testing batch metadata operations...")

    entity_configs = [
        {
            'name': 'Entity_1',
            'sync': 'auto',
            'center': {'x': 100, 'y': 200}
        },
        {
            'name': 'Entity_2',
            'sync': 'push',  # Not auto sync
            'center': {'x': 200, 'y': 300}
        },
        {
            'name': 'Entity_3',
            'sync': 'auto',
            'center': {'x': 300, 'y': 400},
            '_sync': {
                'content_hash': 'existing_hash'  # Already has metadata
            }
        }
    ]

    summary = ensure_sync_metadata_complete(entity_configs, 'viewport')

    assert summary['initialized_count'] == 1, "Should initialize 1 entity (Entity_1)"
    assert summary['validated_count'] == 2, "Should validate 2 auto sync entities"
    assert '_sync' in entity_configs[0], "Entity_1 should have sync metadata"
    assert '_sync' not in entity_configs[1], "Entity_2 should not have sync metadata (not auto)"
    print(f"✓ Batch operation summary: {summary}")

    print("Batch metadata operations tests passed!\n")


def test_error_recovery():
    """Test error recovery and validation."""
    print("Testing error recovery...")

    # Test corrupted hash
    corrupted_config = {
        'name': 'Corrupted_Entity',
        'center': {'x': 100, 'y': 200},
        '_sync': {
            'content_hash': 'invalid_hash',  # Too short
            'last_sync_time': 'invalid_time'  # Wrong type
        }
    }

    validation = validate_and_repair_sync_metadata(corrupted_config, 'viewport')

    assert not validation['valid'], "Should detect corruption"
    assert 'fixed_invalid_hash' in validation['repairs_made'], "Should repair hash"
    assert 'fixed_invalid_timestamp' in validation['repairs_made'], "Should repair timestamp"
    assert len(corrupted_config['_sync']['content_hash']) == 64, "Should have valid hash now"
    print(f"✓ Repaired corrupted metadata: {validation['repairs_made']}")

    print("Error recovery tests passed!\n")


def test_integration_mock_workflow():
    """Test integration with mocked DXF operations."""
    print("Testing integration workflow...")

    # Mock project settings
    project_settings = {
        'auto_conflict_resolution': 'prompt',
        'viewports': [
            {
                'name': 'Integration_Test_Viewport',
                'center': {'x': 500, 'y': 600},
                'width': 800,
                'height': 400,
                'sync': 'auto'
            }
        ]
    }

    # Mock project loader
    mock_project_loader = Mock()
    mock_project_loader.write_yaml_file.return_value = True

    # Create viewport manager
    viewport_manager = ViewportManager(
        project_settings=project_settings,
        script_identifier="Test Script",
        name_to_aci={'white': 7},
        project_loader=mock_project_loader
    )

    # Test metadata initialization
    entity_configs = project_settings['viewports']
    summary = ensure_sync_metadata_complete(entity_configs, 'viewport', viewport_manager)

    assert summary['initialized_count'] == 1, "Should initialize the auto sync viewport"
    assert '_sync' in entity_configs[0], "Viewport should have sync metadata"
    print(f"✓ Integration test initialized metadata: {summary}")

    # Test hash calculation for this specific viewport
    config_hash = viewport_manager._calculate_entity_hash(entity_configs[0])
    assert len(config_hash) == 64, "Manager should calculate valid hash"
    print(f"✓ Manager calculated hash: {config_hash[:12]}...")

    print("Integration workflow tests passed!\n")


def run_all_tests():
    """Run all test functions."""
    print("=" * 60)
    print("HASH-BASED AUTO SYNC INTEGRATION TESTS")
    print("=" * 60)
    print()

    test_functions = [
        test_hash_calculation,
        test_metadata_initialization,
        test_change_detection,
        test_yaml_cleaning,
        test_batch_metadata_operations,
        test_error_recovery,
        test_integration_mock_workflow
    ]

    passed = 0
    failed = 0

    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} FAILED: {str(e)}")
            failed += 1
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Auto sync system is ready for use.")
    else:
        print("⚠️  Some tests failed. Please review and fix issues before deployment.")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
