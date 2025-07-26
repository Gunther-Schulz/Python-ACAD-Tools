# Handle Recovery Mechanism

## Overview

The auto sync system now includes a **Handle Recovery Mechanism** that prevents false entity deletions when AutoCAD operations change DXF handles unexpectedly.

## The Problem This Solves

Previously, if AutoCAD changed an entity's handle (during `AUDIT`, `RECOVER`, block operations, etc.), the auto sync system would:

1. Look for the entity using the stored handle
2. Not find it (because handle changed)  
3. **Assume the user deleted it**
4. **Remove the entity from YAML** ❌

This was dangerous because legitimate AutoCAD operations could cause data loss!

## How Recovery Works

The new system adds a **name-based recovery layer**:

```python
# Auto sync logic (simplified):
if yaml_exists and not dxf_exists:  # Entity "missing"
    stored_handle = config['_sync']['dxf_handle']
    
    if stored_handle:
        # 🔄 NEW: Try recovery before assuming deletion
        recovered_entity = find_by_name_ignoring_handle_validation(entity_name)
        
        if recovered_entity:
            # ✅ Found by name! Handle probably changed
            new_handle = str(recovered_entity.dxf.handle)
            log_info(f"RECOVERED: {entity_name} handle {stored_handle} → {new_handle}")
            
            # Update handle tracking and continue sync
            repair_handle_tracking(recovered_entity, config)
            continue_with_normal_sync()
            
        else:
            # 🗑️ Really not found anywhere - assume deletion
            remove_from_yaml()
```

## Scenarios Protected Against

### ✅ **Handle Changes**
- **AUDIT** command fixes corruption
- **RECOVER** operations  
- **Block redefinition**
- **PURGE** operations
- **Database regeneration**
- **File corruption recovery**

**Before**: Entity deleted from YAML ❌  
**After**: Handle updated, sync continues ✅

### ✅ **Real Deletions**  
- User deletes entity in AutoCAD
- Entity not found by handle OR name
- Correctly removed from YAML ✅

## Recovery Process

1. **Handle Lookup**: Try stored `dxf_handle` (fast O(1))
2. **Recovery Attempt**: If handle fails, search by name (O(n))
3. **Handle Repair**: If found by name, update handle tracking
4. **Continue Sync**: Process normally with corrected handle
5. **Fallback**: If name also fails, assume real deletion

## Logging Examples

### Successful Recovery
```
⚠️  Entity 'Main_Viewport' not found by handle F6ED - attempting name-based recovery
✅ RECOVERED: Entity 'Main_Viewport' found with new handle F7AB (was F6ED)
✅ REPAIRED: viewport 'Main_Viewport' handle tracking updated to F7AB
🔄 RECOVERED+SYNC: Entity 'Main_Viewport' recovered, no changes detected
```

### Real Deletion
```
⚠️  Entity 'Old_Viewport' not found by handle F6EE - attempting name-based recovery
🗑️  Entity 'Old_Viewport' not found by handle OR name - assuming user deletion
```

## Configuration

No configuration needed! Recovery is automatic for entities with `sync: auto`.

The recovery mechanism:
- **Zero overhead** when handles are stable
- **Automatic fallback** when handles change
- **Preserves performance** with handle-first lookup
- **Maintains safety** with name-based backup

## Implementation Details

### Entity Managers Updated
- **ViewportManager**: Recovery in all layouts
- **TextInsertManager**: Recovery in modelspace/paperspace  
- **BlockInsertManager**: Recovery across all spaces

### Handle Validation Bypass
Recovery uses `_find_entity_by_name_ignoring_handle_validation()` which:
- Finds entities by XDATA name matching
- Skips handle validation that would reject "copied" entities
- Returns raw entity for handle repair

### XDATA Repair
When recovery succeeds:
1. Updates `_sync.dxf_handle` in YAML
2. Re-attaches correct XDATA with new handle
3. Maintains all other sync metadata
4. Continues normal sync processing

## Migration Impact

### ✅ **Backward Compatible**
- Existing `push`/`pull`/`skip` sync modes unchanged
- Only affects entities with `sync: auto`
- No configuration changes needed

### ✅ **Safe Rollback**
- Recovery only adds safety, doesn't change core logic
- Can be disabled by reverting to name-only lookup
- No data format changes

## Best Practices

### When Recovery Helps Most
- Interactive AutoCAD workflows
- Files shared between multiple users
- Projects with complex block hierarchies
- Workflows involving AUDIT/RECOVER operations

### Monitoring Recovery
Watch logs for recovery events:
- Frequent recoveries might indicate systemic issues
- Document operations that trigger handle changes
- Consider handle stability in workflow design

## Technical Notes

### Performance Impact
- **Minimal**: Handle lookup remains O(1) for stable handles
- **Reasonable**: Name search is O(n) only on handle failures  
- **Efficient**: XDATA-based name search is optimized

### Entity Identity
- Recovery preserves entity identity through names
- Handle changes don't break tracking
- Conflict resolution works normally after recovery

### Error Handling
- Recovery failures fall back to normal push/pull
- Malformed entities handled gracefully
- All recovery attempts logged for debugging

---

## Example: Your Viewport Case

With this protection, your viewport with `sync: auto` is now safe from:

```yaml
# Before recovery: Risk of deletion if handle F6ED changes
# After recovery: Handle automatically updated if changed

- center:
    x: 906.4332528307149
    y: 355.8964827525824
  width: 177.1475149288962
  height: 94.68235633125732
  viewCenter:
    x: 278937.3899984032
    y: 5964758.852966763
  scale: 33.361749
  sync: auto
  _sync:
    dxf_handle: 10AF6  # ← This gets updated automatically if it changes
```

**Your concern about brittleness is now addressed!** 🛡️ 