# Hash-Based Auto Sync - Usage Example

This example demonstrates how to set up and use the new hash-based auto sync system.

## Step 1: Configure Project Settings

**projects/MyProject/project.yaml**
```yaml
projectName: "MyProject"
projectCrs: "EPSG:25832"
dxfFile: "path/to/project.dxf"

# Set global conflict resolution policy
auto_conflict_resolution: prompt  # User chooses on conflicts
```

## Step 2: Configure Viewports for Auto Sync

**projects/MyProject/viewports.yaml**
```yaml
viewports:
- name: Main_View
  center: {x: 100, y: 200}
  width: 400
  height: 300
  scale: 1.0
  sync: auto  # Enable auto sync
  _sync:
    # System will auto-populate these fields:
    content_hash: null
    last_sync_time: null
    sync_source: null

- name: Detail_View
  center: {x: 500, y: 600}
  width: 200
  height: 150
  scale: 2.0
  sync: auto
  _sync:
    conflict_policy: yaml_wins  # Override global policy

# Global viewport settings
sync: auto  # Default for viewports without explicit sync setting
discovery: true
deletion_policy: auto
```

## Step 3: Configure Text Inserts for Auto Sync

**projects/MyProject/text_inserts.yaml**
```yaml
textInserts:
- name: Project_Title
  text: "My Project Title"
  position: {type: absolute, x: 50, y: 800}
  targetLayer: Plantext
  sync: auto  # Enable auto sync
  _sync:
    content_hash: null  # Auto-populated

- name: Scale_Text
  text: "Scale 1:1000"
  position: {type: absolute, x: 50, y: 50}
  sync: auto

# Global text settings
sync: auto
discovery: true
```

## Step 4: First Run - Initialization

When you first run the sync system:

```bash
python main.py MyProject
```

**What happens:**
1. System detects `sync: auto` entities without metadata
2. Automatically initializes `_sync` metadata with current content hashes
3. Updates YAML files with calculated hashes
4. Creates/updates DXF entities as needed

**Console output:**
```
Initializing sync metadata for entity 'Main_View' with hash: abc123def456...
Initializing sync metadata for entity 'Detail_View' with hash: def456abc123...
Initialized sync metadata for 2 viewport(s)
Successfully updated viewports.yaml with sync changes
```

## Step 5: Edit YAML - Auto Push to DXF

Edit the YAML file:

**viewports.yaml** (change Main_View scale)
```yaml
- name: Main_View
  center: {x: 100, y: 200}
  width: 400
  height: 300
  scale: 1.5  # Changed from 1.0
  sync: auto
  _sync:
    content_hash: "abc123def456..."  # Old hash
    last_sync_time: 1703120000
    sync_source: "yaml"
```

**Next sync run:**
```
Auto sync analysis for 'Main_View': YAML changed: True, DXF changed: False
YAML changed for 'Main_View', pushing to DXF
Successfully updated Main_View viewport from YAML
```

**Result:** DXF viewport updated with new scale, YAML hash updated

## Step 6: Edit in AutoCAD - Auto Pull to YAML

1. Open DXF in AutoCAD
2. Move the Detail_View viewport to a new position
3. Save the DXF file

**Next sync run:**
```
Auto sync analysis for 'Detail_View': YAML changed: False, DXF changed: True
DXF changed for 'Detail_View', pulling to YAML
Successfully updated Detail_View configuration from DXF
```

**Result:** YAML updated with new position, sync metadata updated

## Step 7: Conflict Resolution - Both Sides Changed

**Scenario:**
1. User edits scale in YAML: `scale: 2.5`
2. User moves viewport in AutoCAD
3. Both sides now have changes

**Next sync run:**
```
⚠️  SYNC CONFLICT DETECTED for entity 'Detail_View'
Both YAML and DXF versions have been modified.

What would you like to do?
1. Use YAML version (overwrite DXF)
2. Use DXF version (overwrite YAML)
3. Skip this entity (leave both unchanged)
4. Show details

Enter your choice (1-4): 1
```

**User chooses 1 (YAML wins):**
```
User chose: YAML wins for entity 'Detail_View'
Resolving conflict for 'Detail_View': YAML wins
Successfully pushed YAML changes to DXF
```

## Step 8: Automated Conflict Resolution

For entities with specific policies:

**viewports.yaml**
```yaml
- name: Detail_View
  # ... properties
  _sync:
    conflict_policy: yaml_wins  # Automatic resolution
```

**Next conflict:**
```
Conflict detected for viewport 'Detail_View' - both YAML and DXF changed
Conflict resolved: YAML wins for entity 'Detail_View' (policy: yaml_wins)
Successfully resolved conflict automatically
```

## Step 9: Migration from Manual Sync

**Before (manual sync):**
```yaml
viewports:
- name: Old_Viewport
  sync: push  # Manual push mode
- name: New_Viewport
  sync: pull  # Manual pull mode
```

**After (mixed mode):**
```yaml
viewports:
- name: Old_Viewport
  sync: push  # Keep existing manual sync
- name: New_Viewport
  sync: auto  # Upgrade to auto sync
  _sync:
    content_hash: null  # Will be initialized
```

## Benefits Demonstrated

### Automatic Direction Detection
- No need to remember whether to push or pull
- System detects actual content changes
- Eliminates sync mistakes

### Conflict Resolution
- Clear detection when both sides change
- Multiple resolution strategies
- User control over conflict handling

### Backward Compatibility
- Existing `push`/`pull` settings continue working
- Gradual migration possible
- Mix auto and manual sync as needed

### Error Recovery
- Automatic metadata initialization
- Validation and repair of corrupted data
- Graceful handling of missing information

This system provides intelligent, automatic sync direction detection while maintaining full user control over conflict resolution and migration strategies.
