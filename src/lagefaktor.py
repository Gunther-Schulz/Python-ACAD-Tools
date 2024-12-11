import geopandas as gpd
import pandas as pd
from pathlib import Path
from src.utils import log_debug, log_warning, log_error, log_info

class LagefaktorProcessor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.config = self._load_lagefaktor_config()
        
    def _load_lagefaktor_config(self):
        """Load the lagefaktor configuration from the project."""
        try:
            config_path = Path(self.project_loader.folder_prefix) / 'lagefaktor.yaml'
            if not config_path.exists():
                log_warning(f"Lagefaktor config not found at {config_path}")
                return []
            return self.project_loader.load_yaml(config_path)
        except Exception as e:
            log_error(f"Error loading lagefaktor config: {str(e)}")
            return []

    def process_construction_scores(self, layer_processor):
        """Process construction scores for all configured areas."""
        log_info(f"-------------Processing construction scores for {len(self.config)} areas")
        for area_config in self.config:
            if 'construction' not in area_config:
                continue
                
            area_name = area_config['name']
            grz = area_config.get('grz', 0.0)
            construction_config = area_config['construction']
            
            try:
                # Process each construction layer
                for layer_config in construction_config['layers']:
                    layer_name = layer_config['layer']
                    base_value = layer_config['baseValue']
                    
                    if layer_name not in layer_processor.all_layers:
                        log_warning(f"Layer {layer_name} not found for construction calculation")
                        continue
                        
                    # Get the layer's GeoDataFrame
                    gdf = layer_processor.all_layers[layer_name]
                    if gdf is None or len(gdf) == 0:
                        log_warning(f"Layer {layer_name} is empty")
                        continue
                        
                    # Add base value to features
                    gdf['base_value'] = base_value
                    
                    # Calculate Lagefaktor based on area
                    gdf['lagefaktor'] = gdf.geometry.area.apply(
                        lambda x: self._get_lagefaktor_value(x, construction_config['lagefaktorValues'])
                    )
                    
                    # Calculate construction scores
                    scored_gdf = self._calculate_construction_scores(gdf, grz, area_name)
                    
                    # Update the layer in layer_processor
                    layer_processor.all_layers[layer_name] = scored_gdf
                    
                    log_debug(f"Processed construction scores for layer: {layer_name}")
                    
            except Exception as e:
                log_error(f"Error processing construction scores for area {area_name}: {str(e)}")

    def _get_lagefaktor_value(self, area, lagefaktor_values):
        """Determine the lagefaktor value based on area."""
        for range_str, value in lagefaktor_values.items():
            # Handle the special case for ranges like '>100<625'
            if '>' in range_str and '<' in range_str:
                min_val = float(range_str.split('<')[0].replace('>', ''))
                max_val = float(range_str.split('<')[1])
                if min_val < area < max_val:
                    return value
            # Handle simple less than case
            elif '<' in range_str:
                max_val = float(range_str.replace('<', ''))
                if area < max_val:
                    return value
            # Handle greater than case
            elif '>' in range_str:
                min_val = float(range_str.replace('>', ''))
                if area > min_val:
                    return value
                    
        log_warning(f"No matching lagefaktor value found for area: {area}")
        return 1.0  # Default value if no match found

    def _calculate_construction_scores(self, features, grz, area_name):
        """Calculate construction scores for features."""
        # Add score calculation
        def calculate_score(row):
            area = row.geometry.area
            base_value = row['base_value']
            lagefaktor = row['lagefaktor']
            
            # Calculate intermediate values
            base_times_lage = base_value * lagefaktor
            initial_value = base_times_lage * area
            
            # TODO: Replace with actual GRZ factors from configuration
            factor_a = 1.0  # These should come from configuration
            factor_b = 1.0
            factor_c = 0.0
            
            adjusted_value = initial_value * factor_a
            factor_sum = factor_b + factor_c
            final_value = adjusted_value * factor_sum
            
            # Log calculation steps
            calculation_steps = {
                'area': area,
                'base_value': base_value,
                'lagefaktor': lagefaktor,
                'base_times_lage': base_times_lage,
                'initial_value': initial_value,
                'adjusted_value': adjusted_value,
                'final_value': final_value
            }
            
            # Add calculation steps to row attributes
            if 'attributes' not in row:
                row['attributes'] = {}
            row['attributes']['calculation'] = calculation_steps
            
            return round(final_value, 2)
        
        # Calculate scores
        features['score'] = features.apply(calculate_score, axis=1)
        
        # Log the total score for this area
        total_score = features['score'].sum()
        log_info(f"Total construction score for area {area_name}: {total_score:.2f}")
        
        log_debug(f"Calculated construction scores for area: {area_name}")
        return features
