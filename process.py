import geopandas as gpd
import ezdxf
import matplotlib.pyplot as plt
import sys
import json


def load_project_settings(project_name):
    with open('projects.json', 'r') as file:
        projects = json.load(file)['projects']
        project = next(
            (project for project in projects if project['name'] == project_name), None)
        return project


def get_layer_info(project_settings, layer_name):
    shapefile = next((layer['shapeFile']
                     for layer in project_settings['layers'] if layer['name'] == layer_name), None)
    label = next((layer['label'] for layer in project_settings['layers']
                 if layer['name'] == layer_name), None)
    return shapefile, label


def load_template(project_settings):
    if project_settings['useTemplate']:
        doc = ezdxf.readfile(TEMPLATE_DXF)
        return doc


def load_shapefile(file_path):
    gdf = gpd.read_file(file_path)
    gdf = gdf.set_crs(CRS, allow_override=True)
    return gdf


def geoms_missing(gdf: gpd.GeoDataFrame, coverage: dict) -> set:
    return set(coverage["parcelList"]).difference(gdf[PARCEL_LABEL])

# Filter parcels


def filter_parcels(parcel, flur, gemarkung, gemeinde, coverage):

    parcels_missing = geoms_missing(parcel, coverage)

    if not parcels_missing:
        print("No parcels missing.")

    buffered_flur = flur[flur[FLUR_LABEL].isin(
        coverage["flurList"])].unary_union.buffer(-10)
    buffered_gemeinde = gemeinde[gemeinde[GEMEINDE_LABEL].isin(
        coverage["gemeindeList"])].unary_union.buffer(-10)
    buffered_gemarkung = gemarkung[gemarkung[GEMARKUNG_LABEL].isin(
        coverage["gemarkungList"])].unary_union.buffer(-10)

    selected_parcels = parcel[parcel[PARCEL_LABEL].isin(
        coverage["parcelList"])]

    selected_parcels_mask = parcel.index.isin(selected_parcels.index)

    # Create a boolean mask for parcels that intersect with buffered_flur
    flur_mask = parcel.intersects(buffered_flur)
    gemeinde_mask = parcel.intersects(buffered_gemeinde)
    gemarkung_mask = parcel.intersects(buffered_gemarkung)

    # Use logical AND between two boolean masks for indexing
    result = parcel[selected_parcels_mask &
                    flur_mask & gemeinde_mask & gemarkung_mask]

    # fig, ax = plt.subplots()
    # result.plot(ax=ax, color='green')
    # plt.show()

    return result


# Conditional buffer


def conditional_buffer(source_geom, target_geom, distance):
    if any(source_geom.intersects(geom) for geom in target_geom['geometry']):
        return source_geom.buffer(-distance)
    else:
        return source_geom.buffer(distance)

# Apply conditional buffering to flur geometries


def apply_conditional_buffering(source_geom, target_geom, distance):
    # TODO: If it crosses Geltungsbereich, increase distance by x. Try by using a combination of target_parcels and geltungsbereich
    source_geom['geometry'] = source_geom['geometry'].apply(
        lambda x: conditional_buffer(x, target_geom, distance))
    return source_geom  # This now ensures it returns a GeoDataFrame


def labeled_center_points(source_geom, label):
    # Use representative_point() to get a point within the polygon
    points_within = source_geom.representative_point()
    return gpd.GeoDataFrame(geometry=points_within, data={"label": source_geom[label]})


def add_text_style(doc, text_style_name):
    if text_style_name not in doc.styles:
        doc.styles.new(name=text_style_name, dxfattribs={
                       'font': 'Arial.ttf', 'height': 0.1})


def add_text(msp, text, x, y, layer_name, style_name):
    msp.add_text(text, dxfattribs={
                 'style': style_name,
                 'layer': layer_name,
                 # Initial insertion point, might not be used depending on alignment
                 'insert': (x, y),
                 'align_point': (x, y),  # Actual point for alignment
                 'halign': 1,  # Center alignment
                 'valign': 1   # Middle alignment
                 })


def add_text_to_center(msp, labeled_centroid_points_df, layer_name, style_name=None):
    if style_name is None or not msp.styles.has_entry(style_name):
        style_name = "default"
    for index, row in labeled_centroid_points_df.iterrows():
        x, y = row['geometry'].coords[0]
        add_text(msp, row['label'], x, y, layer_name, style_name)


# Add geometries to DXF


def add_geometries(msp, geometries, layer_name, close=False):
    for geom in geometries:
        if geom is None:
            print(
                f"Warning: None geometry encountered in layer '{layer_name}'")
        elif geom.geom_type == 'Polygon':
            points = [(x, y) for x, y in geom.exterior.coords]
            msp.add_lwpolyline(points, close=close, dxfattribs={
                               'layer': layer_name})
        elif geom.geom_type == 'MultiPolygon':
            for polygon in geom.geoms:
                points = [(x, y) for x, y in polygon.exterior.coords]
                msp.add_lwpolyline(points, close=close, dxfattribs={
                                   'layer': layer_name})


def add_points_to_dxf(msp, points, layer_name):
    for point in points:
        msp.add_point(point, dxfattribs={'layer': layer_name})


def add_from_template(msp, template_dxf):
    doc = ezdxf.readfile(template_dxf)
    # msp.add_entities(doc.modelspace())
    # add Layout1
    msp.add_entities(doc.modelspace().get_layout('Layout1'))

# Main function


def add_layer(doc, layer_name, color):
    if not doc.layers.has_entry(layer_name):
        doc.layers.new(name=layer_name, dxfattribs={'color': color})


def main():
    parcels = load_shapefile(PARCEL_SHAPEFILE)
    flur = load_shapefile(FLUR_SHAPEFILE)
    gemarkung = load_shapefile(GEMARKUNG_SHAPEFILE)
    gemeinde = load_shapefile(GEMEINDE_SHAPEFILE)

    target_parcels = filter_parcels(
        parcels, flur, gemarkung, gemeinde, COVERAGE)
    # check if this actually works by switching sides
    flur = apply_conditional_buffering(flur, target_parcels, 2)
    geltungsbereich = target_parcels['geometry'].unary_union

    parcel_points = labeled_center_points(parcels, PARCEL_LABEL)
    flur_points = labeled_center_points(flur, FLUR_LABEL)
    gemeinde_points = labeled_center_points(gemeinde, GEMEINDE_LABEL)
    gemarkung_points = labeled_center_points(gemarkung, GEMARKUNG_LABEL)

    if project_settings['useTemplate']:
        doc = load_template(project_settings)
    else:
        doc = ezdxf.new('R2010', setup=True)

    # Add defaults
    add_text_style(doc, 'default')

    # This is optional and only useful if we want to set some attributes to the layer. Otherwise defaults are used
    add_layer(doc, 'Flur', COLORS['Flur'])
    add_layer(doc, 'Gemeinde', COLORS['Gemeinde'])
    add_layer(doc, 'Gemarkung', COLORS['Gemarkung'])
    add_layer(doc, 'Parcel', COLORS['Parcel'])
    add_layer(doc, 'Parcel Number', COLORS['Parcel'])
    add_layer(doc, 'Flur Number', COLORS['Flur'])
    # add_layer(doc, 'Gemeinde Name', COLORS['Gemeinde'])
    # add_layer(doc, 'Gemarkung Name', COLORS['Gemarkung'])

    add_layer(doc, 'Geltungsbereich', 10)
    add_text_style(doc, 'Parcel Number')
    add_text_style(doc, 'Flur Number')
    add_text_style(doc, 'Gemeinde Name')
    add_text_style(doc, 'Gemarkung Name')

    msp = doc.modelspace()

    add_geometries(
        msp, [geltungsbereich], 'Geltungsbereich', True)
    add_geometries(msp, flur['geometry'], 'Flur', True)
    add_geometries(msp, gemeinde['geometry'], 'Gemeinde', True)
    add_geometries(msp, gemarkung['geometry'], 'Gemarkung', True)
    add_geometries(msp, parcels['geometry'], 'Parcel', True)
    add_text_to_center(msp, parcel_points, 'Parcel Number')
    add_text_to_center(msp, flur_points, 'Flur Number')
    add_text_to_center(msp, gemeinde_points, 'Gemeinde Name')
    add_text_to_center(msp, gemarkung_points, 'Gemarkung Name')

    doc.saveas(DXF_FILENAME)
    print(f"Saved {DXF_FILENAME}")


if __name__ == "__main__":
    if len(sys.argv) < 1:
        print("Usage: python process.py <project_name>")

    project_settings = load_project_settings(sys.argv[1])
    if project_settings:
        CRS = project_settings['crs']
        DXF_FILENAME = project_settings['dxfFilename']
        TEMPLATE_DXF = project_settings['template']
        GEMEINDE_SHAPEFILE, GEMEINDE_LABEL = get_layer_info(
            project_settings, "Gemeinde")
        GEMARKUNG_SHAPEFILE, GEMARKUNG_LABEL = get_layer_info(
            project_settings, "Gemarkung")
        FLUR_SHAPEFILE, FLUR_LABEL = get_layer_info(project_settings, "Flur")
        PARCEL_SHAPEFILE, PARCEL_LABEL = get_layer_info(
            project_settings, "Parcel")
        COLORS = {layer['name']: layer['color']
                  for layer in project_settings['layers']}
        COVERAGE = project_settings['coverage']
    # Add your processing logic here

    else:
        print(f"Project {sys.argv[1]} not found.")

    main()
