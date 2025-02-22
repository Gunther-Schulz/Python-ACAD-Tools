#!/bin/bash

# Help message
show_help() {
    echo "Usage: run-hooks.sh [OPTION]"
    echo "Run pre-commit hooks for specific parts of the codebase."
    echo
    echo "Options:"
    echo "  tests     Run only test-related hooks"
    echo "  source    Run only source code hooks"
    echo "  project   Run project-wide hooks"
    echo "  all       Run all hooks"
    echo "  help      Show this help message"
    echo
    echo "Examples:"
    echo "  run-hooks.sh tests    # Run only test hooks"
    echo "  run-hooks.sh source   # Run only source hooks"
    echo "  run-hooks.sh project  # Run project-wide hooks"
    echo "  run-hooks.sh all      # Run all hooks"
}

# Main script logic
case $1 in
    "tests")
        echo "Running test hooks..."
        pre-commit run --hook-stage pre-commit "*-tests"
        ;;
    "source")
        echo "Running source code hooks..."
        pre-commit run --hook-stage pre-commit "*-src"
        ;;
    "project")
        echo "Running project-wide hooks..."
        pre-commit run semgrep pyright
        ;;
    "all")
        echo "Running all hooks..."
        pre-commit run --all-files
        ;;
    "help"|"-h"|"--help"|"")
        show_help
        ;;
    *)
        echo "Error: Unknown option '$1'"
        echo
        show_help
        exit 1
        ;;
esac
