#!/usr/bin/env python3
"""
Migration script to convert existing projects from push/auto folder structure
to the new structure: geom_layers at root + generated/interactive folders.

Usage:
    python migrate_project_structure.py --dry-run    # Preview changes
    python migrate_project_structure.py              # Execute migration
    python migrate_project_structure.py --project ProjectName  # Migrate specific project
"""

import os
import shutil
import argparse
from pathlib import Path

def log_info(message):
    print(f"✓ {message}")

def log_warning(message):
    print(f"⚠ {message}")

def log_error(message):
    print(f"✗ {message}")

def get_projects_dir():
    """Get the projects directory path."""
    return Path("projects")

def find_old_structure_projects():
    """Find all projects that still use the old push/auto structure."""
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        log_warning(f"Projects directory not found: {projects_dir}")
        return []

    old_structure_projects = []

    for project_path in projects_dir.iterdir():
        if project_path.is_dir():
            push_dir = project_path / "push"
            auto_dir = project_path / "auto"

            # Check if project has old structure
            if push_dir.exists() or auto_dir.exists():
                old_structure_projects.append(project_path)
                log_info(f"Found old structure project: {project_path.name}")

    return old_structure_projects

def migrate_single_project(project_path, dry_run=False):
    """Migrate a single project from old to new structure."""
    project_name = project_path.name
    log_info(f"\n{'=' * 50}")
    log_info(f"Migrating project: {project_name}")
    log_info(f"{'=' * 50}")

    push_dir = project_path / "push"
    auto_dir = project_path / "auto"
    generated_dir = project_path / "generated"
    interactive_dir = project_path / "interactive"

    # File mappings: (source_path, destination_path)
    file_mappings = [
        # Move geom_layers.yaml to root
        (push_dir / "geom_layers.yaml", project_path / "geom_layers.yaml"),

        # Move other push files to generated/
        (push_dir / "legends.yaml", generated_dir / "legends.yaml"),
        (push_dir / "path_arrays.yaml", generated_dir / "path_arrays.yaml"),
        (push_dir / "wmts_wms_layers.yaml", generated_dir / "wmts_wms_layers.yaml"),

        # Move auto files to interactive/
        (auto_dir / "text_inserts.yaml", interactive_dir / "text_inserts.yaml"),
        (auto_dir / "block_inserts.yaml", interactive_dir / "block_inserts.yaml"),
        (auto_dir / "viewports.yaml", interactive_dir / "viewports.yaml"),
    ]

    # Create target directories
    directories_to_create = [generated_dir, interactive_dir]

    if dry_run:
        log_info("DRY RUN - No files will be moved")

    # Create directories
    for target_dir in directories_to_create:
        if not target_dir.exists():
            if dry_run:
                log_info(f"Would create directory: {target_dir.relative_to(project_path)}")
            else:
                target_dir.mkdir(parents=True, exist_ok=True)
                log_info(f"Created directory: {target_dir.relative_to(project_path)}")

    # Move files
    files_moved = 0
    files_missing = 0

    for source_path, dest_path in file_mappings:
        if source_path.exists():
            if dest_path.exists():
                log_warning(f"Destination already exists: {dest_path.relative_to(project_path)} (skipping)")
                continue

            if dry_run:
                log_info(f"Would move: {source_path.relative_to(project_path)} → {dest_path.relative_to(project_path)}")
            else:
                try:
                    shutil.move(str(source_path), str(dest_path))
                    log_info(f"Moved: {source_path.relative_to(project_path)} → {dest_path.relative_to(project_path)}")
                    files_moved += 1
                except Exception as e:
                    log_error(f"Failed to move {source_path.relative_to(project_path)}: {e}")
        else:
            files_missing += 1
            if source_path.name != "geom_layers.yaml":  # geom_layers.yaml might not exist in all projects
                log_warning(f"File not found: {source_path.relative_to(project_path)}")

    # Remove old directories if empty
    if not dry_run:
        for old_dir in [push_dir, auto_dir]:
            if old_dir.exists():
                try:
                    if not any(old_dir.iterdir()):  # Directory is empty
                        old_dir.rmdir()
                        log_info(f"Removed empty directory: {old_dir.relative_to(project_path)}")
                    else:
                        log_warning(f"Directory not empty, keeping: {old_dir.relative_to(project_path)}")
                        # List remaining files
                        remaining_files = list(old_dir.iterdir())
                        for file in remaining_files:
                            log_warning(f"  Remaining file: {file.relative_to(project_path)}")
                except Exception as e:
                    log_error(f"Failed to remove directory {old_dir.relative_to(project_path)}: {e}")

    # Summary
    log_info(f"\nMigration summary for {project_name}:")
    log_info(f"  Files moved: {files_moved}")
    log_info(f"  Files missing: {files_missing}")

    return files_moved > 0

def main():
    parser = argparse.ArgumentParser(description="Migrate project folder structure")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without executing them")
    parser.add_argument("--project", type=str,
                       help="Migrate specific project by name")

    args = parser.parse_args()

    if args.dry_run:
        log_info("🔍 DRY RUN MODE - No changes will be made")

    # Get projects to migrate
    if args.project:
        project_path = get_projects_dir() / args.project
        if not project_path.exists():
            log_error(f"Project not found: {args.project}")
            return 1
        projects_to_migrate = [project_path]
    else:
        projects_to_migrate = find_old_structure_projects()

    if not projects_to_migrate:
        log_info("No projects with old structure found. All projects are up to date!")
        return 0

    log_info(f"Found {len(projects_to_migrate)} projects to migrate")

    # Migrate each project
    migrated_count = 0
    for project_path in projects_to_migrate:
        try:
            if migrate_single_project(project_path, dry_run=args.dry_run):
                migrated_count += 1
        except Exception as e:
            log_error(f"Failed to migrate {project_path.name}: {e}")

    # Final summary
    log_info(f"\n{'=' * 60}")
    log_info(f"MIGRATION COMPLETE")
    log_info(f"{'=' * 60}")
    log_info(f"Projects processed: {len(projects_to_migrate)}")
    log_info(f"Projects migrated: {migrated_count}")

    if args.dry_run:
        log_info("\nThis was a dry run. Run without --dry-run to execute the migration.")

    return 0

if __name__ == "__main__":
    exit(main())
