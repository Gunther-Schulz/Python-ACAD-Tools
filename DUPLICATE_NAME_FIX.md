# Duplicate Name Handling Fix

## Problem Identified

The discovery system had a critical bug in duplicate name handling that could cause **data loss**.

### ❌ Previous Broken Logic:
```python
# Generate a name for this unmanaged entity
entity_name = self._generate_entity_name(entity, entity_counter)

# Skip if name already exists in configuration
if entity_name in configured_names:
    entity_counter += 1
    continue  # ❌ ENTITY SKIPPED ENTIRELY!
```

**Problem**: When a duplicate name was detected, the system would:
1. Increment the counter
2. **Skip the entity completely** (no YAML entry created)
3. Entity would be lost and never managed

### ✅ Fixed Logic:
```python
# Generate a name for this unmanaged entity
entity_name = self._generate_entity_name(entity, entity_counter)

# Ensure unique name by incrementing counter if needed
while entity_name in configured_names:
    entity_counter += 1
    entity_name = self._generate_entity_name(entity, entity_counter)
```

**Solution**: When a duplicate name is detected, the system now:
1. Keeps trying new names with incremented counters
2. **Ensures the entity gets a unique name**
3. **No entities are lost**

## Impact by Entity Type

### Blocks ✅ (Already worked correctly)
Block names include counters by design:
- `Block_T-Symbol_455`
- `Block_T-Symbol_456`
- `Block_T-Symbol_457`

**Result**: No impact - blocks already had unique names.

### Text Entities ⚠️ (Potential data loss fixed)
Text names based on content could collide:
- First: `Text_Entwurf_vorhabensbezogener_Bebauungsplan` ✅ Added
- Second identical: **BEFORE**: ❌ Lost forever
- Second identical: **AFTER**: ✅ `Text_Entwurf_vorhabensbezogener_Bebauungsplan_001`

### Viewport Entities ⚠️ (Potential data loss fixed)
Viewport names based on handles, but could still collide:
- First: `Viewport_3DE3` ✅ Added
- Duplicate: **BEFORE**: ❌ Lost forever
- Duplicate: **AFTER**: ✅ `Viewport_3DE4` (or incremented name)

## Real-World Scenarios Fixed

### Scenario 1: Multiple Identical Text Labels
```
DXF contains:
- Text "TITLE" at position (100, 200)
- Text "TITLE" at position (300, 400)  # Same content, different position

BEFORE FIX:
- Only first text would be discovered and managed
- Second text completely ignored

AFTER FIX:
- First: "Text_TITLE"
- Second: "Text_TITLE_001"
- Both texts properly managed
```

### Scenario 2: Copied Viewports
```
User copies viewport with identical properties:

BEFORE FIX:
- Original viewport managed
- Copied viewport lost forever

AFTER FIX:
- Original: "Viewport_3DE3"
- Copy: "Viewport_3DE3_001"
- Both viewports properly managed
```

## Technical Details

### Name Generation Process
1. **Initial name**: Generated using entity-specific logic
2. **Collision check**: Compare against existing YAML names
3. **Resolution**: If collision, increment counter and regenerate
4. **Repeat**: Continue until unique name found

### Counter Management
- **Per-discovery session**: Counter increments during single discovery run
- **Persistent**: Names remain stable once written to YAML
- **Thread-safe**: Single-threaded discovery prevents race conditions

## Benefits

1. **No Data Loss**: All discovered entities get managed
2. **Predictable Names**: Clear numbering scheme for duplicates
3. **Backward Compatible**: Existing entities keep their names
4. **Robust**: Handles any number of duplicates

## Testing

✅ **Verified**: Fix tested successfully with Bibow project
✅ **No Regressions**: All existing functionality still works
✅ **Performance**: Minimal overhead (only for duplicate names)

The duplicate name handling is now **robust and data-loss-free**!
