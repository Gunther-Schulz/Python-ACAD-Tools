# Hash-Based Auto Sync System Guide

## Overview

The auto sync system automatically determines whether to sync from YAML to DXF or from DXF to YAML based on content changes, eliminating the need to manually specify sync directions.

## Key Features

- **Content-based change detection**: Uses SHA-256 hashes to detect actual content changes
- **Automatic sync direction**: Syncs from changed side to unchanged side
- **Conflict resolution**: Handles cases where both sides have changed
- **Backward compatibility**: Works alongside existing push/pull/skip modes

## Configuration

### Global Settings (project.yaml)

```yaml
# Set global conflict resolution policy
auto_conflict_resolution: prompt  # Options: prompt, yaml_wins, dxf_wins, skip
```

### Entity-Level Settings

#### Viewports (viewports.yaml)

```yaml
viewports:
- name: Main_Viewport
  center: {x: 100, y: 100}
  width: 200
  height: 150
  sync: auto  # Enable auto sync for this viewport
  _sync:
    content_hash: null  # Auto-populated by system
    conflict_policy: yaml_wins  # Override global policy

# Global viewport settings
sync: auto  # Default for viewports without explicit sync setting
```

#### Text Inserts (text_inserts.yaml)

```yaml
textInserts:
- name: Title_Text
  text: "Project Title"
  position: {type: absolute, x: 50, y: 800}
  sync: auto  # Enable auto sync for this text
  _sync:
    content_hash: null  # Auto-populated by system

# Global text settings
sync: auto  # Default for texts without explicit sync setting
```

## Sync Modes

| Mode | Description |
|------|-------------|
| `auto` | **NEW**: Automatic hash-based sync direction detection |
| `push` | Always sync YAML → DXF |
| `pull` | Always sync DXF → YAML |
| `skip` | Never sync |

## Change Detection Logic

### No Conflict (Simple Cases)
- **Only YAML changed**: Automatically syncs YAML → DXF
- **Only DXF changed**: Automatically syncs DXF → YAML
- **No changes**: Skips sync entirely

### Conflict (Both Sides Changed)
When both YAML and DXF have changed, the system uses conflict resolution policies:

#### Global Conflict Policies
1. **`prompt`** (default): Interactive user choice
2. **`yaml_wins`**: Always prefer YAML content
3. **`dxf_wins`**: Always prefer DXF content
4. **`skip`**: Skip conflicted entities

#### Entity-Level Override
```yaml
_sync:
  conflict_policy: yaml_wins  # Override global policy for this entity
```

## Interactive Conflict Resolution

When `conflict_policy: prompt` is used, you'll see:

```
⚠️  SYNC CONFLICT DETECTED for entity 'Main_Viewport'
Both YAML and DXF versions have been modified.

What would you like to do?
1. Use YAML version (overwrite DXF)
2. Use DXF version (overwrite YAML)
3. Skip this entity (leave both unchanged)
4. Show details

Enter your choice (1-4):
```

## Sync Metadata

The system automatically manages sync metadata in YAML files:

```yaml
_sync:
  content_hash: "sha256:abc123..."  # Content fingerprint
  last_sync_time: 1703123456        # Unix timestamp
  sync_source: "yaml"               # Last sync direction
  conflict_policy: "prompt"         # Optional policy override
```

**Important**: Don't manually edit `_sync` metadata - it's automatically managed.

## Migration from Manual Sync

### Existing Projects
- Current `push`/`pull`/`skip` settings continue working unchanged
- Add `sync: auto` to individual entities or globally when ready
- Mix auto sync with manual sync as needed

### Gradual Adoption
```yaml
viewports:
- name: Old_Viewport
  sync: push  # Keep existing manual sync
- name: New_Viewport
  sync: auto  # Use new auto sync
```

## Best Practices

### When to Use Auto Sync
- ✅ Entities you edit in both YAML and CAD
- ✅ Collaborative workflows with multiple editors
- ✅ Uncertain sync direction scenarios

### When to Use Manual Sync
- ✅ One-way sync workflows (always YAML→DXF or DXF→YAML)
- ✅ Entities with complex custom logic
- ✅ Legacy workflows that work well

### Conflict Prevention
- Coordinate with team members on who edits what
- Use entity-level conflict policies for predictable resolution
- Test auto sync on non-critical entities first

## Troubleshooting

### Missing Sync Metadata
- System automatically initializes metadata on first auto sync
- Missing metadata is rebuilt from available information

### Hash Inconsistencies
- System recalculates hashes if inconsistencies detected
- Check logs for detailed hash comparison information

### Conflict Resolution Issues
- Verify `auto_conflict_resolution` setting in project.yaml
- Check entity-level `conflict_policy` overrides
- Use `sync: skip` temporarily to avoid problematic entities

## Example Workflows

### Setup New Project for Auto Sync
1. Set global policy: `auto_conflict_resolution: prompt`
2. Configure entities: `sync: auto`
3. Run first sync to initialize metadata
4. Edit either YAML or DXF - system handles sync direction

### Convert Existing Project
1. Keep current sync settings working
2. Add `sync: auto` to one entity for testing
3. Gradually convert more entities
4. Update global defaults when ready

### Team Workflow
1. Set global policy: `auto_conflict_resolution: prompt`
2. Use entity-level policies for known patterns:
   - `conflict_policy: yaml_wins` for design data
   - `conflict_policy: dxf_wins` for field updates
3. Regular sync runs with conflict resolution as needed
