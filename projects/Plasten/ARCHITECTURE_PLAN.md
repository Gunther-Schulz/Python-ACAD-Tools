# Plasten Project - Clean Architecture Plan

## 🎯 Overview

This document describes the complete layer structure and calculation logic for the Plasten solar project.

---

## Layer Structure

### SECTION 1: INPUT LAYERS (from shapefiles)

#### Cadastral Boundaries
- **Flur** - Field boundaries → synced to DXF
- **Parcel** - Parcel boundaries → NOT synced (already in DXF)
- **Gemarkung** - District boundaries → synced to DXF
- **Gemeinde** - Municipality boundaries → synced to DXF

#### Natural Features
- **Wald** - Forest polygons → synced to DXF with hatching
- **Biotope Input** - Biotope areas → NOT synced
- **Geschütze Biotope** - Protected biotopes → NOT synced

#### Infrastructure
- **FG_Unterirdisch** - Underground utility lines → synced to DXF
- **FG_Oberirdisch** - Overhead utility lines → synced to DXF
- **Ontras_FG_buffer_4** - Gas line 4m zone → NOT synced
- **Ontras_FG_buffer_2** - Gas line 2m zone → NOT synced
- **Straßenflurstückskante** - Road parcel edge → NOT synced
- **Gebäude 150m Abstand** - Building shapefile → NOT synced
- **Baum_abstand** - Tree distance line shapefile → NOT synced

#### Other
- **Blendschutzzaun** - Anti-glare fence → synced to DXF
- **Baum Points** - Tree points → synced to DXF
- **Baufeld Label Points** - Label points → NOT synced (for processing)
- **EinAusfahrt Line** → synced to DXF

---

### SECTION 2: BUFFER LAYERS (calculated, NOT synced)

#### Utility Line Buffers (round caps for line ends, round joins)
- **FG Line** = merge(FG_Unterirdisch + FG_Oberirdisch)
- **FG Buffer** = FG Line + 20m (round caps/joins, quadSegs: 32)
- **Ontras_FG_buffer_4 Buffer** = Ontras_FG_buffer_4 + 4m (round)
- **Ontras_FG_buffer_2 Buffer** = Ontras_FG_buffer_2 + 2m (round)
- **Gastrasse Buffer** = dissolve(Ontras_FG_buffer_4 Buffer + Ontras_FG_buffer_2 Buffer)

#### Natural Feature Buffers (for Baugrenze exclusion only)
- **Waldabstand** = Wald + 30m buffer (round caps/joins, quadSegs: 32) - used to keep Baugrenze 30m from forest
- **Baumabstand 20m Buffer** = Baum_abstand + 20m buffer (round caps/joins) - used to keep Baugrenze 20m from tree lines

#### Infrastructure Buffers
- **Straßenflurstückskante Buffer 20m** = Straßenflurstückskante + 20m (round)
- **Gebäude 150m Abstand Buffer** = Gebäude shapefile + 150m (mitre)

#### Combined Biotopes
- **Biotope** = dissolve(Biotope Input + Geschütze Biotope)
- **Geschütze Biotope 2** = Geschütze Biotope + 0.5m (for styling, synced)

---

### SECTION 3: WORKING AREA CALCULATION (NOT synced)

#### Three Parcel Groups

**Geltungsbereich NW Working:**
- Parcels: 1, 2, 4, 6, 7, 14
- Location: Flur 1, Groß Plasten
- Exclusions: Wald (forest polygons completely removed)

**Geltungsbereich NO Working:**
- Parcels: 24/8, 24/9
- Location: Flur 1, Groß Plasten
- Exclusions: Wald (forest polygons completely removed)

**Geltungsbereich S Working:**
- Parcels: 41/1
- Location: Flur 2, Klein Plasten
- Exclusions: Wald (forest polygons completely removed)

---

### SECTION 4: AGRIPV CALCULATION (planning designation)

**AgriPV (calculated, NOT synced yet):**
1. Start: Geltungsbereich NW Working + NO Working + S Working
2. Exclude: Biotope only
3. Filter: Remove polygons < 200m²

**Note:** AgriPV does NOT exclude utility lines, roads, or tree lines - these can run through or be at the edge of AgriPV. Only Wald and Biotope are excluded.

---

### SECTION 5: FINAL OUTPUT LAYERS (synced to DXF)

#### Planning Boundaries (follow AgriPV outline)

**Geltungsbereich NW/NO/S:**
- Geltungsbereich NW = AgriPV ∩ (NW parcels) → synced with geltungsbereich style
- Geltungsbereich NO = AgriPV ∩ (NO parcels) → synced with geltungsbereich style
- Geltungsbereich S = AgriPV ∩ (S parcels) → synced with geltungsbereich style

**Styling Buffers:**
- Geltungsbereich NW 2 = Geltungsbereich NW + 2m buffer
- Geltungsbereich NO 2 = Geltungsbereich NO + 2m buffer
- Geltungsbereich S 2 = Geltungsbereich S + 2m buffer

**Hatching:**
- Geltungsbereich Hatch NW (hatching on Geltungsbereich NW)
- Geltungsbereich Hatch NO (hatching on Geltungsbereich NO)
- Geltungsbereich Hatch S (hatching on Geltungsbereich S)

#### Solar Panel Planning Area

**AgriPV (synced):**
- Style: baufeld
- With hatching (AgriPV Schraffur)

#### Construction Boundary (where panels actually go)

**Baugrenze (calculated):**
1. Start: AgriPV
2. Buffer: -20m (mitre joins)
3. Exclude (each with its specific buffer distance):
   - Biotope (0m - complete exclusion)
   - FG Buffer (20m from utility lines)
   - Gastrasse Buffer (2m and 4m zones from gas lines)
   - Waldabstand (30m from Wald edge)
   - Straßenflurstückskante Buffer (20m from road edge)
   - Baumabstand Buffer (20m from tree lines)
   - Gebäude Buffer (150m from buildings)
4. Synced with baugrenze style

**Note:** Each infrastructure type has its own specific buffer distance. Utility lines can run through AgriPV but Baugrenze must maintain clearance from their buffer zones.

**Baugrenze 2** = Baugrenze - 0.4m (styling)

#### Biotope Display

**Biotope Innerhalb Geltungsbereich:**
- Biotope ∩ (all Geltungsbereich Working areas)
- Synced to DXF (if needed)

---

### SECTION 6: REPORTS (area calculations, NOT synced)

#### Biotope Reports
- **Biotop Report NW** = Biotope ∩ Geltungsbereich NW
- **Biotop Report S** = Biotope ∩ Geltungsbereich S

#### Baugrenze Reports
- **Baugrenze Report NW** = Baugrenze ∩ Geltungsbereich NW
- **Baugrenze Report NO** = Baugrenze ∩ Geltungsbereich NO
- **Baugrenze Report S** = Baugrenze ∩ Geltungsbereich S

#### AgriPV Reports
- **AgriPV Report NW** = AgriPV ∩ Geltungsbereich NW
- **AgriPV Report NO** = AgriPV ∩ Geltungsbereich NO
- **AgriPV Report S** = AgriPV ∩ Geltungsbereich S

#### AgriPV Streifen Reports (dead zones)
- **AgriPV Streifen Report NW** = (AgriPV - Baugrenze) ∩ Geltungsbereich NW
- **AgriPV Streifen Report NO** = (AgriPV - Baugrenze) ∩ Geltungsbereich NO
- **AgriPV Streifen Report S** = (AgriPV - Baugrenze) ∩ Geltungsbereich S

#### Geltungsbereich Area Reports
- Geltungsbereich NW report (area calculations)
- Geltungsbereich NO report (area calculations)
- Geltungsbereich S report (area calculations)

---

## Visual Result

```
┌──────────────────────────────────────────────────────────────┐
│                                                               │
│  Geltungsbereich (follows AgriPV outline)                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                          │  │
│  │  ██████████████ AgriPV (planning zone) ████████████     │  │
│  │  ████████ [biotope] ████████████████████████████████    │  │
│  │  ███████████████████████████████████████████████████    │  │
│  │  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░███████     │  │
│  │  ██░░ Dead zone (30m from Wald) ░░░░░░░░░░░███████     │  │
│  │  ██░░┌─────────────────────────────┐░░░░░░███████     │  │
│  │  ██░░│                             │░░░░░░███████     │  │
│  │  ██░░│      BAUGRENZE              │░░░░░░███████     │  │
│  │  ██░░│  (actual solar panels)      │░░░░░░███████     │  │
│  │  ██░░│                             │░░░░░░███████     │  │
│  │  ██░░│  [small biotope excluded]   │░░░░░░███████     │  │
│  │  ██░░│                             │░░░░░░███████     │  │
│  │  ██░░└─────────────────────────────┘░░░░░░███████     │  │
│  │  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░███████     │  │
│  │  ████████████████████████████████████████████████     │  │
│  │  ██████ [biotope] █████████████████████████████        │  │
│  │                                                          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  [Wald - completely excluded] ← AgriPV stops at Wald edge   │
│  [Utility lines] ← can run through AgriPV, 20m buffer zones │
│                    excluded only from Baugrenze              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**Legend:**
- `█` = AgriPV (planning designation)
- `░` = Dead zone (AgriPV but not Baugrenze)
- `┌─┐` = Baugrenze (actual panels can go here)

---

## Key Relationships

1. **Geltungsbereich** = exact outline of AgriPV (per parcel NW/NO/S)
2. **AgriPV** = parcels - Wald - Biotope (can go right up to Wald edge, utility lines can run through it)
3. **Baugrenze** = AgriPV with 20m inset + infrastructure-specific buffer exclusions
4. **Dead zones** = AgriPV area where no actual panels (AgriPV - Baugrenze)

### What AgriPV Excludes vs What Baugrenze Excludes

**AgriPV excludes (very permissive):**
- ✅ Wald (forest polygons - complete exclusion)
- ✅ Biotope (protected nature areas - complete exclusion)
- ❌ Does NOT exclude utility lines (they can run through AgriPV)
- ❌ Does NOT exclude roads (AgriPV can extend to road edges)
- ❌ Does NOT exclude tree lines (AgriPV can extend to tree lines)

**Baugrenze additionally excludes (more restrictive):**
- ✅ Everything AgriPV excludes (Wald, Biotope)
- ✅ 20m inset from AgriPV edge
- ✅ Utility buffer zones (20m FG, 2m/4m Gastrasse)
- ✅ 30m buffer from Wald edge (Waldabstand)
- ✅ 20m buffer from road edges (Straßenflurstückskante)
- ✅ 20m buffer from tree lines (Baumabstand)
- ✅ 150m buffer from buildings (Gebäude)

---

## Buffer Specifications

### Join Styles
- **Utility/infrastructure buffers**: `round` caps and joins (for smooth curves along lines)
- **AgriPV inset**: `mitre` joins (for sharp corners)
- **Baugrenze inset**: `mitre` joins (for sharp corners)

### Distances

**AgriPV exclusions:**
- **Wald**: Complete exclusion (forest polygons removed)
- **Biotope**: Complete exclusion (protected nature areas removed)

**Baugrenze exclusions (in addition to AgriPV exclusions):**
- **AgriPV edge**: 20m inset from AgriPV boundary
- **Waldabstand**: 30m buffer from Wald edge (keeps Baugrenze 30m away from forest)
- **FG Buffer**: 20m buffer from utility lines (keeps Baugrenze 20m away from utilities)
- **Gastrasse Buffer**: 2m and 4m buffers from gas lines (keeps Baugrenze away from gas infrastructure)
- **Straßenflurstückskante Buffer**: 20m buffer from road edge
- **Baumabstand Buffer**: 20m buffer from tree lines
- **Gebäude Buffer**: 150m buffer from buildings

**Important:** These buffers (Waldabstand, FG Buffer, etc.) do NOT affect AgriPV - they ONLY affect Baugrenze. AgriPV can extend right up to Wald, utility lines can run through it, etc. The buffers create "dead zones" where AgriPV exists but Baugrenze cannot be.

---

## Dead Zone Summary

| Feature | AgriPV Exclusion | Baugrenze Buffer/Exclusion | Resulting Dead Zone |
|---------|------------------|---------------------------|---------------------|
| Wald edge | Complete (stops at Wald edge) | Waldabstand 30m buffer | **30m** (from Wald edge to Baugrenze) |
| FG utility lines | None (can run through AgriPV) | FG Buffer 20m | **20m** (on each side of utility line) |
| Gas lines (Gastrasse) | None (can run through AgriPV) | Gastrasse Buffer 2m/4m | **2m/4m** (on each side) |
| Straßenflurstückskante | None (can be at edge) | 20m buffer | **20m** (from road edge) |
| Baumabstand lines | None (can be at edge) | 20m buffer | **20m** (from tree line) |
| Buildings | None (can be at edge) | 150m buffer | **150m** (from building) |
| Biotope | Complete exclusion | Complete exclusion | **0m** (excluded from both) |
| AgriPV edge | N/A | 20m inset from AgriPV | **20m** (inside AgriPV boundary) |

**Key insight:** AgriPV is very permissive - only excludes Wald and Biotope completely. Waldabstand, utility buffers, etc. are NOT excluded from AgriPV - they are ONLY used to calculate Baugrenze exclusions. Dead zones are the areas where AgriPV exists but Baugrenze cannot be, due to these buffer requirements.

---

## Important Notes

1. **No circular dependencies**: All layers follow a clear downstream calculation order
2. **Geltungsbereich follows AgriPV**: The planning boundary outline matches the solar area extent
3. **Dead zones exist**: Areas within AgriPV but outside Baugrenze where panels cannot be installed
4. **Biotopes are excluded**: Small scattered patches removed from both AgriPV and Baugrenze
5. **All topology operations use `useBufferTrick: true`**: To prevent gaps and overlaps from floating-point precision issues

