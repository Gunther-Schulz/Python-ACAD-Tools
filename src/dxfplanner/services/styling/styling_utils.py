from typing import TypeVar, Optional, Type, Any, get_args, get_origin
from pydantic import BaseModel
# import logging # For debug print

# logger = logging.getLogger(__name__) # For debug print

T = TypeVar('T', bound=BaseModel)

def _get_actual_model_type(annotation: Any) -> Optional[Type[BaseModel]]:
    """Extracts the actual Pydantic model type from a type annotation, handling Optional/Union."""
    origin = get_origin(annotation)
    if origin is Optional: # Handles Optional[Model]
        args = get_args(annotation)
        if args and hasattr(args[0], 'mro') and BaseModel in args[0].mro():
            return args[0]
    elif origin is list: # Example for List[Model], adapt if needed for other generics
        args = get_args(annotation)
        if args and hasattr(args[0], 'mro') and BaseModel in args[0].mro():
            # This would return the type of items in the list,
            # but merge_style_components is for merging model instances, not list of models directly.
            # For recursive merge, you'd typically iterate the list and merge items.
            # So, for now, we consider List[Model] not a direct candidate for *this* specific check.
            return None
    elif hasattr(annotation, 'mro') and BaseModel in annotation.mro(): # Handles Model directly
        return annotation
    return None

def merge_style_components(
    model_cls: Type[T],
    base: Optional[T],
    override: Optional[T]
) -> T:
    if not base and not override:
        return model_cls()
    if not override:
        return base.model_copy(deep=True) if base else model_cls()
    if not base:
        return override.model_copy(deep=True)

    base_data = base.model_dump(exclude_unset=True)
    override_data = override.model_dump(exclude_none=True)

    merged_data = base_data.copy()

    for key, override_value in override_data.items():
        if key in base_data:
            base_value = base_data[key]
            field_annotation_info = model_cls.model_fields.get(key)

            actual_model_type_for_field = None
            if field_annotation_info:
                actual_model_type_for_field = _get_actual_model_type(field_annotation_info.annotation)

            is_base_dict = isinstance(base_value, dict)
            is_override_dict = isinstance(override_value, dict)
            can_recurse = actual_model_type_for_field is not None

            if (is_base_dict and is_override_dict and can_recurse):
                nested_base = actual_model_type_for_field(**base_value)
                nested_override = actual_model_type_for_field(**override_value)

                merged_nested_instance = merge_style_components(actual_model_type_for_field, nested_base, nested_override)
                merged_data[key] = merged_nested_instance.model_dump(exclude_none=True)
            else:
                merged_data[key] = override_value
        else:
            merged_data[key] = override_value

    return model_cls(**merged_data)
