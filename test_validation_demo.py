#!/usr/bin/env python3
"""
Demonstration script for enhanced geom_layers.yaml validation capabilities.

This script shows how the validation system catches:
1. Unknown settings and typos
2. Non-existent style presets
3. Missing file references
4. Invalid operation types
5. Inline style validation
6. And much more...
"""

import yaml
import os
from typing import Dict, Any

# Add the src directory to the path for imports
import sys
sys.path.insert(0, 'src')

from src.domain.config_validation import ConfigValidationService, ConfigValidationError


def load_test_config(file_path: str) -> Dict[str, Any]:
    """Load a YAML configuration file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def demonstrate_validation():
    """Demonstrate the comprehensive validation capabilities."""
    print("🔍 Enhanced geom_layers.yaml Validation Demonstration")
    print("=" * 60)

    # Test files
    test_files = [
        ("projects/test_project/geom_layers.yaml", "✅ Valid Configuration"),
        ("projects/test_project/geom_layers_validation_test.yaml", "❌ Invalid Configuration (Test)")
    ]

    for file_path, description in test_files:
        print(f"\n📁 Testing: {file_path}")
        print(f"📋 Description: {description}")
        print("-" * 40)

        if not os.path.exists(file_path):
            print(f"⚠️  File not found: {file_path}")
            continue

        try:
            # Load the configuration
            config_data = load_test_config(file_path)

            # Create validator with project base path
            project_base = os.path.dirname(file_path)
            validator = ConfigValidationService(base_path=project_base)

            # Validate the configuration
            validated_config = validator.validate_project_config(config_data, file_path)

            # Check for warnings
            warnings = validator.validation_warnings
            if warnings:
                print(f"⚠️  {len(warnings)} Validation Warnings:")
                for i, warning in enumerate(warnings, 1):
                    print(f"   {i}. {warning}")
            else:
                print("✅ No validation warnings")

            print("✅ Configuration is valid!")

        except ConfigValidationError as e:
            print(f"❌ Validation Failed: {e}")

            if hasattr(e, 'validation_errors') and e.validation_errors:
                print(f"\n🚨 {len(e.validation_errors)} Validation Errors:")
                for i, error in enumerate(e.validation_errors, 1):
                    print(f"   {i}. {error}")

            # Also show warnings if any
            warnings = validator.validation_warnings
            if warnings:
                print(f"\n⚠️  {len(warnings)} Validation Warnings:")
                for i, warning in enumerate(warnings, 1):
                    print(f"   {i}. {warning}")

        except Exception as e:
            print(f"💥 Unexpected error: {e}")


def demonstrate_specific_validations():
    """Demonstrate specific validation features."""
    print("\n\n🎯 Specific Validation Features")
    print("=" * 60)

    # Test unknown key detection with suggestions
    print("\n1. 📝 Unknown Key Detection with Suggestions")
    print("-" * 30)

    test_layer = {
        'name': 'test',
        'geojsonFile': '@data.test',
        'labelColum': 'name',  # Typo
        'unknownSetting': 'value',  # Unknown
        'styl': 'building_style'  # Typo
    }

    validator = ConfigValidationService()
    validator._validate_layer_keys(test_layer, 'test_layer')

    for warning in validator.validation_warnings:
        print(f"   ⚠️  {warning}")

    # Test style validation
    print("\n2. 🎨 Style Validation")
    print("-" * 20)

    # Mock available styles
    available_styles = {
        'building_style': {},
        'road_style': {},
        'point_style': {}
    }

    test_style_layer = {
        'name': 'test',
        'geojsonFile': '@data.test',
        'style': 'building_styl'  # Typo
    }

    validator = ConfigValidationService()
    validator._validate_layer_style(test_style_layer, 'test_layer', available_styles)

    for error in validator.validation_errors:
        print(f"   ❌ {error}")

    # Test inline style validation
    print("\n3. 🖌️  Inline Style Validation")
    print("-" * 25)

    test_inline_style = {
        'layer': {
            'color': 'red',
            'colr': 'blue',  # Typo
            'unknownProp': 'value'  # Unknown
        },
        'hatch': {
            'pattern': 'SOLID',
            'scal': 1.0,  # Typo
            'invalidProp': 'test'  # Unknown
        }
    }

    validator = ConfigValidationService()
    validator._validate_inline_style(test_inline_style, 'test_layer')

    for warning in validator.validation_warnings:
        print(f"   ⚠️  {warning}")


def show_validation_summary():
    """Show a summary of what the validation system checks."""
    print("\n\n📊 Validation Coverage Summary")
    print("=" * 60)

    validations = {
        "✅ File Path Validation": [
            "File extension checking",
            "File existence verification",
            "Path alias resolution",
            "Directory traversal prevention"
        ],
        "✅ Style Validation": [
            "Style preset existence checking",
            "Typo detection with suggestions",
            "Inline style structure validation",
            "Style property validation"
        ],
        "✅ Layer Configuration": [
            "Unknown setting detection",
            "Typo suggestions (Levenshtein distance)",
            "Data source validation",
            "Multiple source conflict detection"
        ],
        "✅ Operation Validation": [
            "Operation type validation",
            "Parameter validation",
            "Layer reference checking",
            "Cross-layer dependency validation"
        ],
        "✅ General Validation": [
            "Duplicate name detection",
            "Required field checking",
            "Type validation",
            "Cross-field consistency"
        ]
    }

    for category, checks in validations.items():
        print(f"\n{category}")
        for check in checks:
            print(f"   • {check}")


if __name__ == "__main__":
    try:
        demonstrate_validation()
        demonstrate_specific_validations()
        show_validation_summary()

        print("\n\n🎉 Validation Demonstration Complete!")
        print("=" * 60)
        print("The enhanced validation system now provides:")
        print("• Comprehensive error detection")
        print("• Intelligent typo suggestions")
        print("• File existence checking")
        print("• Style preset validation")
        print("• Unknown setting detection")
        print("• And much more!")

    except Exception as e:
        print(f"💥 Demo failed: {e}")
        import traceback
        traceback.print_exc()
