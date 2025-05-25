#!/usr/bin/env python3
"""
Comprehensive demonstration script for all enhanced validation capabilities.

This script demonstrates the full range of validation features including:
1. Performance warnings and thresholds
2. Operation parameter validation
3. Style property validation
4. Security checks
5. Data integrity validation
6. Cross-field dependency validation
7. And much more...
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


def demonstrate_comprehensive_validation():
    """Demonstrate all enhanced validation capabilities."""
    print("🔍 Comprehensive Enhanced Validation Demonstration")
    print("=" * 70)

    # Test files
    test_files = [
        ("projects/test_project/geom_layers.yaml", "✅ Valid Configuration"),
        ("projects/test_project/geom_layers_validation_test.yaml", "❌ Basic Validation Issues"),
        ("projects/test_project/geom_layers_comprehensive_validation_test.yaml", "❌ Comprehensive Validation Issues")
    ]

    for file_path, description in test_files:
        print(f"\n📁 Testing: {file_path}")
        print(f"📋 Description: {description}")
        print("-" * 50)

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


def demonstrate_specific_enhanced_validations():
    """Demonstrate specific enhanced validation features."""
    print("\n\n🎯 Enhanced Validation Features")
    print("=" * 70)

    from src.domain.config_validation import ConfigValidators, ValidationRegistry

    # Test performance validation
    print("\n1. 📊 Performance Validation")
    print("-" * 30)

    try:
        ConfigValidators.validate_buffer_distance(15000.0)
    except ValueError as e:
        print(f"   ❌ {e}")

    try:
        operations = [{'type': 'buffer'} for _ in range(12)]
        ConfigValidators.validate_operation_chain_length(operations)
    except ValueError as e:
        print(f"   ❌ {e}")

    # Test style property validation
    print("\n2. 🎨 Style Property Validation")
    print("-" * 35)

    try:
        ConfigValidators.validate_text_attachment_point("INVALID_POINT")
    except ValueError as e:
        print(f"   ❌ {e}")

    try:
        ConfigValidators.validate_flow_direction("INVALID_FLOW")
    except ValueError as e:
        print(f"   ❌ {e}")

    try:
        ConfigValidators.validate_cap_style("invalid_cap")
    except ValueError as e:
        print(f"   ❌ {e}")

    # Test operation parameter validation
    print("\n3. ⚙️  Operation Parameter Validation")
    print("-" * 40)

    try:
        ConfigValidators.validate_spatial_predicate("invalid_predicate")
    except ValueError as e:
        print(f"   ❌ {e}")

    try:
        ConfigValidators.validate_join_style("invalid_join")
    except ValueError as e:
        print(f"   ❌ {e}")

    # Test column validation
    print("\n4. 📋 Column Reference Validation")
    print("-" * 35)

    available_columns = ['name', 'id', 'area', 'type']
    try:
        ConfigValidators.validate_column_name("nam", available_columns)
    except ValueError as e:
        print(f"   ❌ {e}")

    try:
        ConfigValidators.validate_column_name("Name", available_columns)
    except ValueError as e:
        print(f"   ❌ {e}")

    # Test security validation
    print("\n5. 🔒 Security Validation")
    print("-" * 25)

    validator = ConfigValidationService()
    validator._validate_path_aliases({
        'data': {
            'dangerous': '../../../etc/passwd'
        }
    })

    for warning in validator.validation_warnings:
        print(f"   ⚠️  {warning}")


def show_enhanced_validation_summary():
    """Show a comprehensive summary of all validation capabilities."""
    print("\n\n📊 Enhanced Validation Coverage Summary")
    print("=" * 70)

    validations = {
        "✅ Performance Validation": [
            "Buffer distance thresholds (10km max)",
            "File size warnings (100MB max)",
            "Operation chain length limits (10 max)",
            "Memory usage warnings (512MB min)",
            "Feature count warnings (50k max)"
        ],
        "✅ Operation Parameter Validation": [
            "Buffer: cap_style, join_style, resolution",
            "Transform: CRS validation for source/target",
            "Filter: spatial predicate validation",
            "Scale: positive scale factor validation",
            "Rotate: required angle parameter",
            "Missing required parameter detection"
        ],
        "✅ Style Property Validation": [
            "Text: attachment points, flow direction, spacing",
            "Layer: linetype patterns, transparency ranges",
            "Hatch: pattern validation, scale factors",
            "Style consistency checks (frozen vs plot)",
            "Color validation (ACI codes, names)"
        ],
        "✅ Data Integrity Validation": [
            "Column reference validation with suggestions",
            "Boolean type checking for flags",
            "Numeric range validation",
            "Empty string detection",
            "Case-sensitive column matching"
        ],
        "✅ Security Validation": [
            "Path traversal detection (../ patterns)",
            "Path alias security warnings",
            "File extension validation",
            "Directory existence checking",
            "Permission validation for output paths"
        ],
        "✅ Dependency Validation": [
            "Circular dependency detection",
            "Layer reference validation",
            "Operation dependency chains",
            "Style preset existence checking",
            "Cross-field consistency validation"
        ],
        "✅ Configuration Structure": [
            "Unknown setting detection with suggestions",
            "Typo detection (Levenshtein distance)",
            "Required field validation",
            "Type validation for all fields",
            "Nested structure validation"
        ]
    }

    for category, checks in validations.items():
        print(f"\n{category}")
        for check in checks:
            print(f"   • {check}")


def demonstrate_validation_categories():
    """Demonstrate validation organized by categories."""
    print("\n\n🏷️  Validation Categories")
    print("=" * 70)

    categories = {
        "🚨 ERRORS (Block Processing)": [
            "Missing required fields",
            "Invalid data types",
            "Non-existent file references",
            "Invalid CRS specifications",
            "Circular dependencies",
            "Unknown operation types",
            "Invalid parameter values"
        ],
        "⚠️  WARNINGS (Allow with Notice)": [
            "Performance threshold exceeded",
            "Unknown configuration keys",
            "Typos with suggestions",
            "Security risks (path traversal)",
            "Memory usage concerns",
            "Style conflicts",
            "Case mismatches"
        ],
        "💡 SUGGESTIONS (Helpful Hints)": [
            "Alternative spellings for typos",
            "Similar column names",
            "Performance optimization tips",
            "Best practice recommendations",
            "Configuration improvements"
        ]
    }

    for category, items in categories.items():
        print(f"\n{category}")
        for item in items:
            print(f"   • {item}")


if __name__ == "__main__":
    try:
        demonstrate_comprehensive_validation()
        demonstrate_specific_enhanced_validations()
        show_enhanced_validation_summary()
        demonstrate_validation_categories()

        print("\n\n🎉 Comprehensive Validation Demonstration Complete!")
        print("=" * 70)
        print("The enhanced validation system now provides:")
        print("• 🔍 Comprehensive error detection")
        print("• 🧠 Intelligent typo suggestions")
        print("• 📁 File existence and size checking")
        print("• 🎨 Style preset and property validation")
        print("• ⚙️  Operation parameter validation")
        print("• 📊 Performance threshold monitoring")
        print("• 🔒 Security risk detection")
        print("• 🔗 Dependency and consistency checking")
        print("• 📋 Column reference validation")
        print("• 💡 Helpful suggestions and warnings")
        print("\nTotal validation checks: 50+ different types!")

    except Exception as e:
        print(f"💥 Demo failed: {e}")
        import traceback
        traceback.print_exc()
