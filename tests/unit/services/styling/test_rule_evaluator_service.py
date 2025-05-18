import unittest
from unittest.mock import MagicMock, call
import logging

from dxfplanner.services.styling.rule_evaluator_service import RuleEvaluatorService

class TestRuleEvaluatorService(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock(spec=logging.Logger)
        self.service = RuleEvaluatorService(logger=self.mock_logger)

    def test_evaluate_condition_equals_string(self):
        self.assertTrue(self.service.evaluate_condition("city == 'New York'", {"city": "New York"}))
        self.assertFalse(self.service.evaluate_condition("city == 'Boston'", {"city": "New York"}))
        self.assertTrue(self.service.evaluate_condition("city = 'NewYork'", {"city": "NewYork"})) # Test single =
        self.assertTrue(self.service.evaluate_condition("city == \"New York\"", {"city": "New York"})) # Double quotes

    def test_evaluate_condition_equals_int(self):
        self.assertTrue(self.service.evaluate_condition("population == 1000", {"population": 1000}))
        self.assertFalse(self.service.evaluate_condition("population == 2000", {"population": 1000}))
        self.assertTrue(self.service.evaluate_condition("population == 1000", {"population": "1000"})) # String attr, num value

    def test_evaluate_condition_equals_float(self):
        self.assertTrue(self.service.evaluate_condition("area == 12.5", {"area": 12.5}))
        self.assertFalse(self.service.evaluate_condition("area == 10.0", {"area": 12.5}))
        self.assertTrue(self.service.evaluate_condition("area == 12.5", {"area": "12.5"}))
        self.assertTrue(self.service.evaluate_condition("area == 1.25e1", {"area": 12.5}))

    def test_evaluate_condition_equals_bool(self):
        self.assertTrue(self.service.evaluate_condition("is_capital == true", {"is_capital": True}))
        self.assertTrue(self.service.evaluate_condition("is_capital == True", {"is_capital": True}))
        self.assertFalse(self.service.evaluate_condition("is_capital == false", {"is_capital": True}))
        self.assertTrue(self.service.evaluate_condition("is_capital == 'true'", {"is_capital": True}))
        self.assertTrue(self.service.evaluate_condition("is_capital == 1", {"is_capital": True})) # Attr is bool, val is 1
        self.assertTrue(self.service.evaluate_condition("is_active == true", {"is_active": "true"})) # Attr is string "true"
        self.assertTrue(self.service.evaluate_condition("is_active == true", {"is_active": "True"}))
        self.assertFalse(self.service.evaluate_condition("is_active == false", {"is_active": "true"}))

    def test_evaluate_condition_not_equals(self):
        self.assertTrue(self.service.evaluate_condition("city != 'Boston'", {"city": "New York"}))
        self.assertFalse(self.service.evaluate_condition("city != 'New York'", {"city": "New York"}))
        self.assertTrue(self.service.evaluate_condition("population != 2000", {"population": 1000}))

    def test_evaluate_condition_greater_than(self):
        self.assertTrue(self.service.evaluate_condition("population > 500", {"population": 1000}))
        self.assertFalse(self.service.evaluate_condition("population > 1000", {"population": 1000}))
        self.assertTrue(self.service.evaluate_condition("value > 5.0", {"value": "10"}))

    def test_evaluate_condition_less_than(self):
        self.assertTrue(self.service.evaluate_condition("population < 2000", {"population": 1000}))
        self.assertFalse(self.service.evaluate_condition("population < 1000", {"population": 1000}))

    def test_evaluate_condition_greater_than_or_equals(self):
        self.assertTrue(self.service.evaluate_condition("population >= 1000", {"population": 1000}))
        self.assertTrue(self.service.evaluate_condition("population >= 500", {"population": 1000}))
        self.assertFalse(self.service.evaluate_condition("population >= 2000", {"population": 1000}))

    def test_evaluate_condition_less_than_or_equals(self):
        self.assertTrue(self.service.evaluate_condition("population <= 1000", {"population": 1000}))
        self.assertTrue(self.service.evaluate_condition("population <= 2000", {"population": 1000}))
        self.assertFalse(self.service.evaluate_condition("population <= 500", {"population": 1000}))

    def test_evaluate_condition_contains(self):
        self.assertTrue(self.service.evaluate_condition("name CONTAINS 'York'", {"name": "New York"}))
        self.assertFalse(self.service.evaluate_condition("name CONTAINS 'Boston'", {"name": "New York"}))
        self.assertTrue(self.service.evaluate_condition("name contains 'york'", {"name": "New York"})) # Case insensitive operator
        self.assertTrue(self.service.evaluate_condition("description CONTAINS 123", {"description": "Order 12345"}))

    def test_evaluate_condition_not_contains(self):
        self.assertTrue(self.service.evaluate_condition("name NOT_CONTAINS 'Boston'", {"name": "New York"}))
        self.assertFalse(self.service.evaluate_condition("name NOT_CONTAINS 'York'", {"name": "New York"}))
        self.assertTrue(self.service.evaluate_condition("name not contains 'boston'", {"name": "New York"}))

    def test_evaluate_condition_in(self):
        self.assertTrue(self.service.evaluate_condition("status IN active,pending", {"status": "active"}))
        self.assertTrue(self.service.evaluate_condition("status IN 'active', 'pending'", {"status": "pending"}))
        self.assertFalse(self.service.evaluate_condition("status IN complete,failed", {"status": "active"}))
        self.assertTrue(self.service.evaluate_condition("id IN 1,2,3", {"id": 2}))
        self.assertTrue(self.service.evaluate_condition("id IN 1,2,3", {"id": "2"}))

    def test_evaluate_condition_not_in(self):
        self.assertTrue(self.service.evaluate_condition("status NOT_IN complete,failed", {"status": "active"}))
        self.assertFalse(self.service.evaluate_condition("status NOT_IN active,pending", {"status": "active"}))

    def test_evaluate_condition_exists(self):
        self.assertTrue(self.service.evaluate_condition("email EXISTS", {"email": "test@example.com", "name": "Test"}))
        self.assertFalse(self.service.evaluate_condition("phone EXISTS", {"email": "test@example.com"}))
        self.assertFalse(self.service.evaluate_condition("address EXISTS", {"address": None})) # Exists but is None

    def test_evaluate_condition_not_exists(self):
        self.assertTrue(self.service.evaluate_condition("phone NOT_EXISTS", {"email": "test@example.com"}))
        self.assertFalse(self.service.evaluate_condition("email NOT_EXISTS", {"email": "test@example.com"}))
        self.assertTrue(self.service.evaluate_condition("address NOT_EXISTS", {"address": None})) # Exists but is None means NOT_EXISTS is true

    def test_evaluate_condition_attribute_is_none(self):
        self.assertTrue(self.service.evaluate_condition("middle_name != 'John'", {"middle_name": None}))
        self.assertFalse(self.service.evaluate_condition("middle_name == 'John'", {"middle_name": None}))
        self.assertTrue(self.service.evaluate_condition("middle_name NOT_CONTAINS 'X'", {"middle_name": None}))
        self.assertFalse(self.service.evaluate_condition("middle_name CONTAINS 'X'", {"middle_name": None}))
        self.assertTrue(self.service.evaluate_condition("middle_name NOT_IN X,Y", {"middle_name": None}))
        self.assertFalse(self.service.evaluate_condition("middle_name IN X,Y", {"middle_name": None}))
        # For numeric comparisons, if actual_value is None, it should typically be False
        self.assertFalse(self.service.evaluate_condition("age > 10", {"age": None}))

    def test_unparseable_condition(self):
        self.assertFalse(self.service.evaluate_condition("this is not a valid condition", {"attr": 1}))
        self.mock_logger.warning.assert_called_with("Unparseable style rule condition: 'this is not a valid condition'. Defaulting to False.")

    def test_comparison_error(self):
        # Example: float comparison with a string that cannot be coerced to float
        self.assertFalse(self.service.evaluate_condition("age > 'ten'", {"age": 30}))
        self.mock_logger.debug.assert_any_call(unittest.mock.ANY) # Check that some debug log for error occurred

    def test_key_with_dot_or_hyphen(self):
        self.assertTrue(self.service.evaluate_condition("data.value == 10", {"data.value": 10}))
        self.assertTrue(self.service.evaluate_condition("item-code CONTAINS 'ABC'", {"item-code": "ABC-123"}))

    def test_case_insensitive_operator_matching(self):
        self.assertTrue(self.service.evaluate_condition("name contains 'York'", {"name": "New York"}))
        self.assertTrue(self.service.evaluate_condition("status in active,pending", {"status": "active"}))
        self.assertTrue(self.service.evaluate_condition("email exists", {"email": "test@example.com"}))

if __name__ == '__main__':
    unittest.main()
