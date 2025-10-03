# Buffer/Exclusion Distances by Area Type

## Plasten Project - Zone Exclusion Rules

| Area/Feature Type                      | Buffer Distance | Excludes AgriPV | Excludes Baugrenze | Exclusion Type  | Dead Zone Created | AgriPV Behavior             |
|----------------------------------------|-----------------|-----------------|--------------------|-----------------|--------------------|------------------------------|
| **Wald (Forest)**                      | 30m             | ✓               | ✓                  | Full            | Yes (20m)          | Hard boundary with 10m gap   |
| **Biotope**                            | Full area       | ✓               | ✓                  | Full            | No                 | Complete avoidance           |
| **Moor**                               | 0m              | ✗               | ✓                  | Baugrenze-only  | Yes (full area)    | Extends over, no construction|
| **Einzelbaumlinie (Tree Line)**        | 20m             | ✗               | ✓                  | Baugrenze-only  | Yes (20m)          | Extends to edge              |
| **Straßenflurstückskante (Road Edge)** | 20m             | ✗               | ✓                  | Baugrenze-only  | Yes (20m)          | Extends to edge              |
| **FG Utility Line**                    | 20m (±)         | ✗               | ✓                  | Baugrenze-only  | Yes (40m total)    | Allows crossing              |
| **Gas Lines**                          | 4-8m (±)        | ✗               | ✓                  | Baugrenze-only  | Yes (8-16m total)  | Allows crossing              |
| **Gebäude (Building)**                 | 150m            | ✗               | ✓                  | Baugrenze-only  | Yes (150m radius)  | Overlaps allowed             |
| **Nutzungsartengrenze**                | Boundary line   | ✓               | ✓                  | Boundary        | N/A                | Hard clip (land use limit)   |
| **Geltungsbereich**                    | Follows AgriPV  | N/A             | N/A                | Boundary        | N/A                | Defines legal planning scope |
| **AgriPV Edge (General)**              | 20m inset       | N/A             | ✓                  | Baugrenze-only  | Yes (20m)          | Internal buffer              |

## Classification Legend

- **Full**: Excludes both AgriPV and Baugrenze
- **Baugrenze-only**: AgriPV allowed, only Baugrenze excluded
- **Boundary**: Defines legal/regulatory scope, not an exclusion
- **Dead Zone**: Area within AgriPV but outside Baugrenze
- **(±)**: Buffer applies on both sides of the line

## Key Concepts

### Geltungsbereich (Scope of Validity)
The legal and regulatory boundary that defines where the land use plan/zoning regulations apply. In this project, it follows the AgriPV outline exactly, encompassing the entire planning area.

### AgriPV (Agricultural Photovoltaic Zone)
The solar planning and designation zone. AgriPV can extend to certain boundaries (tree lines, roads, utility lines) but must maintain distance from others (forest, biotopes).

### Baugrenze (Construction Boundary)
The actual area where solar panels can be physically installed. Always more restrictive than AgriPV due to various safety and regulatory buffers.

### Dead Zones
Areas within AgriPV where Baugrenze cannot be placed due to buffer requirements. These are the result of the difference between AgriPV extent and Baugrenze restrictions.

## Notes

- Gas line buffers are project-specific and typically range from 4-8 meters on each side
- The 20m AgriPV edge rule means Baugrenze must always be at least 20m inset from AgriPV boundaries
- Where multiple buffers overlap, the most restrictive applies

### Processing Architecture

**Hard Exclusions** (AgriPV cannot be here):
- Wald + **10m buffer** (creates the 10m gap)
- Biotopes
- Manual exclusions

**Baugrenze Exclusions** (only affects Baugrenze, not AgriPV):
- Moor (0m buffer - stops at edge)
- FG Buffer, Gas Buffer, Building Buffer
- Note: Waldabstand, Roads, Trees NOT included - the 10m gap + 20m inset = 30m from forest, 20m from roads/trees already

**AgriPV Calculation:**
```
AgriPV = (Parcels - Hard Exclusions) → -20m round → +20m bevel → clip to Nutzungsartengrenze
```
The -20m/+20m buffer trick shapes AgriPV to ensure Baugrenze can reach all areas. The -20m round buffer removes acute corners that can't accommodate the 20m inset, then +20m bevel expands back with chamfered (not rounded) corners. This eliminates geometric dead zones while preserving angular character. Finally, AgriPV is clipped to the Nutzungsartengrenze boundary to respect land use constraints.

**Baugrenze Calculation:**
```
Baugrenze = (AgriPV - 20m round inset) - Baugrenze Exclusions
```
The -20m round inset maintains true perpendicular distance from AgriPV at all corners. Then Baugrenze Exclusion zones (Moor, FG, Gas, Buildings) are subtracted for features crossing through AgriPV. Roads, Trees, and Waldabstand are automatically satisfied by the 20m inset at edges.

**Result:** AgriPV extends to utilities/roads/trees and over Moor areas, but maintains 10m gap from Wald and is clipped to Nutzungsartengrenze. Baugrenze is 20m inset from AgriPV AND respects all buffer zones (including Moor).

---

## Implementation Details

### Three Parcel Groups (Critical for Processing)

The project is divided into three separate zones, each requiring independent calculation:

| Zone | Parcels         | Location                      |
|------|-----------------|-------------------------------|
| **NW** | 1, 2, 4, 6, 7, 14 | Flur 1, Groß Plasten          |
| **NO** | 24/8, 24/9        | Flur 1, Groß Plasten          |
| **S**  | 41/1              | Flur 2, Klein Plasten         |

Each zone needs:
- Separate Geltungsbereich calculation
- Independent AgriPV/Baugrenze processing
- Individual area reports

### Additional Output Layers

Beyond the core zones, these features must be generated:

- **EinAusfahrt Line** - Entrance/driveway access
- **Blendschutzzaun** - Anti-glare fence

### Biotope Handling

**Combined Biotope Layer:**
- **Biotope Input** + **Geschütze Biotope** → merged into single **Biotope** layer
- **Geschütze Biotope 2** = Geschütze Biotope + 0.5m buffer (separate styling layer, synced)

**Interior Ring Strategy:**
Biotopes are hard exclusions that create holes in AgriPV and Baugrenze, but the legal planning boundary (Geltungsbereich) needed to be continuous without internal holes. The `removeInteriorRings` operation was applied after intersecting AgriPV with each Geltungsbereich Base zone (NW, NO, S) to fill in these biotope-created holes. This ensured:
- AgriPV and Baugrenze properly avoided biotopes (with holes)
- Geltungsbereich had a clean outer boundary without interior gaps
- Legal planning scope encompassed the biotope areas even though construction couldn't occur there

This strategy is no longer needed but demonstrates a technique for handling features that need different boundary treatment at different regulatory levels.

### Technical Buffer Specifications

**Buffer Join Styles:**
- **Wald 10m Buffer**: `joinStyle: round` (CRITICAL) - Mitre joins create shortcuts at acute angles, allowing AgriPV to get closer than 10m to forest edges at corners
- **Exclusion buffers** (Waldabstand, FG, Gas, Gebäude, Roads, Trees): `joinStyle: round` with `quadSegs: 32` for smooth curves and consistent distances
- **AgriPV -20m shaping**: `joinStyle: round` - Removes acute corners smoothly
- **AgriPV +20m expansion**: `joinStyle: bevel` - Expands back with chamfered corners to preserve geometric character
- **Baugrenze -20m inset**: `joinStyle: round` with `quadSegs: 32` - Maintains true perpendicular 20m distance at all corners, preventing shortcuts at sharp inward angles

**Linetype Scales:**
- **Baugrenze**: 0.5
- **Geltungsbereich**: 1.0
- **Flur**: 0.2

**Linetype Generation:**
- Enabled for: Flur, Gemarkung, Gemeinde, Baugrenze

### Geometry Filters

**Minimum Area Thresholds:**
- **200m²** - AgriPV, Waldabstand, major features
- **10m²** - Smaller features, cleanup operations

**Geometry Type Filtering:**
- **Polygon only** - Applied to AgriPV to remove any line artifacts

### Hatching Layers

Separate hatching/schraffur layers that reference base geometries:

- **Wald Schraffur** → applies hatching to Wald
- **AgriPV Schraffur** → applies hatching to AgriPV
- **Geltungsbereich Hatch NW/NO/S** → applies hatching to respective Geltungsbereich zones

### Label Fields (from Shapefiles)

| Layer      | Label Field |
|------------|-------------|
| Flur       | flurname    |
| Parcel     | label       |
| Gemarkung  | gmkname     |
| Gemeinde   | gen         |

---

## Final Synced Output Layers

These layers are synchronized to DXF (sync: push):

### Core Planning Zones
1. **Geltungsbereich NW** - Planning boundary northwest
2. **Geltungsbereich NO** - Planning boundary northeast  
3. **Geltungsbereich S** - Planning boundary south
4. **Geltungsbereich NW 2** - Styling variant (+2m buffer)
5. **Geltungsbereich NO 2** - Styling variant (+2m buffer)
6. **Geltungsbereich S 2** - Styling variant (+2m buffer)

### Solar Zones
7. **AgriPV** - Solar planning designation zone
8. **AgriPV Schraffur** - Hatching for AgriPV
9. **Baugrenze** - Construction boundary (where panels go)
10. **Baugrenze 2** - Styling variant (-0.4m buffer)

### Context/Reference Layers
11. **Flur** - Field boundaries
12. **Gemarkung** - District boundaries
13. **Gemeinde** - Municipality boundaries
14. **Nutzungsartengrenze** - Land use boundary (clips AgriPV)
15. **Wald** - Forest polygons
16. **Wald Schraffur** - Forest hatching
17. **Moor** - Wetland/moor areas (soft exclusion)

### Infrastructure
18. **FG_Unterirdisch** - Underground utility lines
19. **FG_Oberirdisch** - Overhead utility lines
20. **Gastrasse** - Gas lines
21. **EinAusfahrt Line** - Entrance/access
22. **Blendschutzzaun** - Anti-glare fence

### Biotopes
23. **Geschütze Biotope 2** - Protected biotopes (+0.5m for styling)

