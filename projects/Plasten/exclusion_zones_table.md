# Buffer/Exclusion Distances by Area Type

## Plasten Project - Zone Exclusion Rules

| Area/Feature Type                      | Buffer Distance | Excludes AgriPV | Excludes Baugrenze | Exclusion Type  | Dead Zone Created | AgriPV Behavior             |
|----------------------------------------|-----------------|-----------------|--------------------|-----------------|--------------------|------------------------------|
| **Wald (Forest)**                      | 30m             | ✓               | ✓                  | Full            | Yes (20m)          | Hard boundary with 10m gap   |
| **Biotope**                            | Full area       | ✓               | ✓                  | Full            | No                 | Complete avoidance           |
| **Einzelbaumlinie (Tree Line)**        | 20m             | ✗               | ✓                  | Baugrenze-only  | Yes (20m)          | Extends to edge              |
| **Straßenflurstückskante (Road Edge)** | 20m             | ✗               | ✓                  | Baugrenze-only  | Yes (20m)          | Extends to edge              |
| **FG Utility Line**                    | 20m (±)         | ✗               | ✓                  | Baugrenze-only  | Yes (40m total)    | Allows crossing              |
| **Gas Lines**                          | 4-8m (±)        | ✗               | ✓                  | Baugrenze-only  | Yes (8-16m total)  | Allows crossing              |
| **Gebäude (Building)**                 | 150m            | ✗               | ✓                  | Baugrenze-only  | Yes (150m radius)  | Overlaps allowed             |
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

