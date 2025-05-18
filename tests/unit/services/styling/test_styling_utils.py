import pytest
from typing import Optional
from pydantic import BaseModel

from dxfplanner.services.styling.styling_utils import merge_style_components

# --- Test Pydantic Model ---
class TestStyleProps(BaseModel):
    height: Optional[float] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    count: Optional[int] = None # For testing 0 values

# --- Test Cases ---

def test_merge_both_none():
    result = merge_style_components(TestStyleProps, None, None)
    assert isinstance(result, TestStyleProps)
    assert result.model_dump(exclude_unset=True) == {}

def test_merge_base_only():
    base = TestStyleProps(height=10.0, name="Base")
    result = merge_style_components(TestStyleProps, base, None)
    assert result.height == 10.0
    assert result.name == "Base"
    assert result.is_active is None

def test_merge_override_only():
    override = TestStyleProps(height=20.0, is_active=True)
    result = merge_style_components(TestStyleProps, None, override)
    assert result.height == 20.0
    assert result.name is None
    assert result.is_active is True

def test_merge_override_wins_on_conflict():
    base = TestStyleProps(height=10.0, name="BaseName")
    override = TestStyleProps(height=20.0, is_active=False)
    result = merge_style_components(TestStyleProps, base, override)
    assert result.height == 20.0       # Override wins
    assert result.name == "BaseName"   # From base
    assert result.is_active is False   # From override

def test_merge_disjoint_properties():
    base = TestStyleProps(name="BaseName")
    override = TestStyleProps(height=30.0, is_active=True)
    result = merge_style_components(TestStyleProps, base, override)
    assert result.height == 30.0       # From override
    assert result.name == "BaseName"   # From base
    assert result.is_active is True   # From override

def test_override_with_explicit_none_does_not_nullify_base_value():
    """
    Because override uses model_dump(exclude_none=True), an explicit None
    in an override field will cause that field to be absent from override_data,
    thus preserving the base value.
    """
    base = TestStyleProps(name="Important Base Name", height=5.0)
    override = TestStyleProps(name=None, height=15.0) # name is None

    result = merge_style_components(TestStyleProps, base, override)

    assert result.name == "Important Base Name" # Preserved from base
    assert result.height == 15.0 # Overridden

def test_override_with_zero_values_overwrites_base():
    base = TestStyleProps(height=10.0, count=5, is_active=True)
    override = TestStyleProps(height=0.0, count=0, is_active=False) # Zero/False values

    result = merge_style_components(TestStyleProps, base, override)

    assert result.height == 0.0
    assert result.count == 0
    assert result.is_active is False

def test_override_empty_string_overwrites_base():
    base = TestStyleProps(name="Base Name")
    override = TestStyleProps(name="")
    result = merge_style_components(TestStyleProps, base, override)
    assert result.name == ""

def test_complex_case_multiple_overrides_and_base_fields():
    base = TestStyleProps(height=1.0, name="Initial", is_active=True, count=100)
    override1 = TestStyleProps(height=2.0, name="Override1") # is_active and count are None

    intermediate_result = merge_style_components(TestStyleProps, base, override1)
    assert intermediate_result.height == 2.0
    assert intermediate_result.name == "Override1"
    assert intermediate_result.is_active is True # From base
    assert intermediate_result.count == 100      # From base

    override2 = TestStyleProps(is_active=False, count=None) # height and name are None

    final_result = merge_style_components(TestStyleProps, intermediate_result, override2)
    assert final_result.height == 2.0       # From intermediate (override1)
    assert final_result.name == "Override1"  # From intermediate (override1)
    assert final_result.is_active is False  # From override2
    assert final_result.count == 100         # From intermediate (base) - because override2.count was None
