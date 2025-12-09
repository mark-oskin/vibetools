#!/usr/bin/python3
import sys
import os
import subprocess
import argparse

def parse_design_document(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()
  
    modules = []
    current = None
    desc_lines = []
  
    for line in lines:
        line = line.rstrip('\n')
        if line.startswith('Module: '):
            if current is not None:
                current['description'] = '\n'.join(desc_lines)
                modules.append(current)
            current = {
                'title': line[8:].strip()
            }
            desc_lines = []
        elif current is not None:
            if line.startswith('Short: '):
                current['short'] = line[7:].strip()
            elif line.startswith('Uses: '):
                uses_str = line[6:].strip()
                if uses_str:
                    current['uses'] = [u.strip() for u in uses_str.split(',')]
                else:
                    current['uses'] = []
            else:
                desc_lines.append(line)
  
    if current is not None:
        current['description'] = '\n'.join(desc_lines)
        modules.append(current)
  
    return modules

def generate_module_file(module, build_dir, overwrite_if_same=True):
    short = module['short']
    filename = os.path.join(build_dir, f"{short}.txt")
    content = f"Module: {module['title']}\n"
    content += f"Short: {module['short']}\n"
    if 'uses' in module and module['uses']:
        content += f"Uses: {', '.join(module['uses'])}\n"
    content += f"\n{module['description']}"
  
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            existing_content = f.read()
        if existing_content == content:
            return # No change, skip write to preserve timestamp
        # If not same, proceed to overwrite
  
    with open(filename, 'w') as f:
        f.write(content)

def generate_makefile(top_level, modules, build_dir, model=None, overwrite_if_same=True):
    all_shorts = [m['short'] for m in modules]
    all_built = [s + '.built' for s in all_shorts]
  
    makefile_content = '.PHONY: all\n\n'
    makefile_content += f"all: {' '.join(all_built)}\n\n"
  
    for module in modules:
        short = module['short']
        uses = module.get('uses', [])
        uses_built = [u + '.built' for u in uses]
        uses_source = [u + '.py' for u in uses]
      
        target_deps = [f"{short}.txt"]
        if uses_built:
            target_deps.extend(uses_built)
      
        makefile_content += f"{short}.built: {' '.join(target_deps)}\n"
        cmd = f"vibecl.py --description {short}.txt --complete ../{top_level}"
        if model:
            cmd += f" --model {model}"
        if uses_source:
            cmd += f" --files {' '.join(uses_source)}"

        makefile_content += f"\t{cmd}\n\n"
  
    filename = os.path.join(build_dir, 'Makefile')
    if os.path.exists(filename) and overwrite_if_same:
        with open(filename, 'r') as f:
            existing_content = f.read()
        if existing_content.rstrip() == makefile_content.rstrip():
            return # No change, skip write
  
    with open(filename, 'w') as f:
        f.write(makefile_content)

def main():
    parser = argparse.ArgumentParser(description="Generate module files and Makefile from a design document.")
    parser.add_argument("design_file", help="Path to the design document file.")
    parser.add_argument("--model", type=str, default=None, help="Grok model to use for code generation (passed to vibecl.py).")
    args = parser.parse_args()
  
    design_file = args.design_file
    model = args.model
  
    if not os.path.exists(design_file):
        print(f"Error: Design document '{design_file}' not found.", file=sys.stderr)
        sys.exit(1)
  
    modules = parse_design_document(design_file)
    if not modules:
        print("Warning: No modules found in the design document.", file=sys.stderr)
        sys.exit(0)
  
    build_dir = 'build'
    os.makedirs(build_dir, exist_ok=True)
  
    # Generate individual module files
    for module in modules:
        if 'short' not in module:
            print(f"Warning: Module '{module['title']}' missing 'Short:' line, skipping.", file=sys.stderr)
            continue
        generate_module_file(module, build_dir)
  
    # Generate Makefile
    generate_makefile(design_file, modules, build_dir, model)
  
    print(f"Generated {len(modules)} module files and Makefile in {build_dir}/")
   
    print("Running make...")
    try:
        subprocess.run(['make', 'all'], cwd=build_dir, check=True)
        print("Build complete.")
    except subprocess.CalledProcessError as e:
        print(f"Make failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()