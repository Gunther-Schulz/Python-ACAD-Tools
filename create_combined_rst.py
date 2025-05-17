import os

# Define the root directory to search for .rst files
root_dir = "/home/g/dev/Gunther-Schulz/Python-ACAD-Tools/ezdxf/docs/source"
# Define the output file path
output_file_path = "/home/g/dev/Gunther-Schulz/Python-ACAD-Tools/ezdxf_combined_documentation.rst"

# List to hold all found .rst file paths
rst_files = []

# Walk through the directory tree
for dirpath, dirnames, filenames in os.walk(root_dir):
    for filename in filenames:
        if filename.endswith(".rst"):
            rst_files.append(os.path.join(dirpath, filename))

# Sort the files to ensure a consistent order (optional, but good practice)
rst_files.sort()

# Open the output file in write mode
with open(output_file_path, "w", encoding="utf-8") as outfile:
    for rst_file_path in rst_files:
        try:
            with open(rst_file_path, "r", encoding="utf-8") as infile:
                outfile.write(f"\n\n--- Start of file: {os.path.relpath(rst_file_path, root_dir)} ---\n\n")
                outfile.write(infile.read())
                outfile.write(f"\n\n--- End of file: {os.path.relpath(rst_file_path, root_dir)} ---\n\n")
            print(f"Successfully processed: {rst_file_path}")
        except Exception as e:
            print(f"Error processing file {rst_file_path}: {e}")

print(f"\nAll .rst files have been combined into: {output_file_path}")
