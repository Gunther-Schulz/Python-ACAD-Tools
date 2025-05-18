from typing import AsyncIterator, Dict, Any, Optional
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.operation_schemas import FieldMappingOperationConfig
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class FieldMappingOperation(IOperation[FieldMappingOperationConfig]):
    """Maps feature attributes based on a provided configuration."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: FieldMappingOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        logger.info(
            f"Executing FieldMappingOperation for source_layer: '{config.source_layer}', " # Assuming source_layer on BaseOperationConfig
            f"output: '{config.output_layer_name}'"
        )

        async for feature in features:
            new_attributes: Dict[str, Any] = {}
            # Ensure feature.properties is used and defaults to empty dict if None
            original_properties = feature.properties if feature.properties is not None else {}


            # Apply field map
            for old_field, new_field_or_spec in config.mapping.items():
                if old_field in original_properties:
                    if isinstance(new_field_or_spec, str): # Simple rename
                        new_attributes[new_field_or_spec] = original_properties[old_field]
                    # Current FieldMappingOperationConfig.mapping is Dict[str, str], so no complex spec handling needed here.
                    # elif isinstance(new_field_or_spec, dict):
                    #     target_field_name = new_field_or_spec.get("new_name", old_field)
                    #     new_attributes[target_field_name] = original_properties[old_field]

            # Handle unmapped fields
            if config.drop_unmapped_fields:
                pass # new_attributes already only contains mapped fields
            elif config.copy_unmapped_fields:
                for old_field, old_value in original_properties.items():
                    # Only copy if it wasn't part of the mapping's source fields
                    # AND it's not already in new_attributes (e.g. if mapped to the same name)
                    if old_field not in config.mapping: # Checks if old_field was a *source* in the map
                         if old_field not in new_attributes: # Ensures it wasn't mapped to itself or another field that got copied
                            new_attributes[old_field] = old_value
                    elif config.mapping.get(old_field) == old_field and old_field not in new_attributes: # If mapped to itself, ensure it's copied
                        new_attributes[old_field] = old_value


            yield GeoFeature(geometry=feature.geometry, attributes=new_attributes, crs=feature.crs) # attributes should be properties if GeoFeature expects that

        logger.info(f"FieldMappingOperation completed for source_layer: '{config.source_layer}'") # Assuming source_layer
