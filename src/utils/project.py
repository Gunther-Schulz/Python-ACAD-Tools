"""Utility functions for project management."""

import os
from .base import log_info, create_sample_project

def list_available_projects():
    """List all available projects in the projects directory.
    
    Returns:
        list: List of project names (without .yaml extension)
    """
    projects_dir = 'projects'
    if not os.path.exists(projects_dir):
        os.makedirs(projects_dir)
        log_info(f"Created projects directory: {projects_dir}")
        return []
    
    projects = []
    for file in os.listdir(projects_dir):
        if file.endswith('.yaml'):
            projects.append(file[:-5])  # Remove .yaml extension
    return projects 