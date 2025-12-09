#!/usr/bin/python3
"""
A Python module to generate code using the Grok API from xAI.
Requires the XAI_API_KEY environment variable to be set.
Extended to optionally include file contents and additional context for better code generation.
Merged with vibebuild functionality: if description is a .txt file, parse it as a module design and build.
"""
import os
import sys
import argparse
import requests
import subprocess
from typing import Optional, List, Tuple
def read_file_content(filepath: str) -> Optional[str]:
    """
    Reads the content of a file as a string.
    Assumes text files; for binary, it may not work well.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (IOError, OSError) as e:
        print(f"Error reading file {filepath}: {e}")
        return None
def generate_code(description: str,
                  revise: bool = False,
                  context: Optional[str] = None,
                  files: Optional[List[str]] = None,
                  complete: Optional[str] = None,
                  language: Optional[str] = "Python",
                  model: str = "grok-4-latest") -> Optional[str]:
    """
    Generates code based on a natural language description using the Grok API,
    optionally including additional context and file contents.
 
    Args:
        description (str): A textual description of the program to be written.
        context (Optional[str]): Additional textual context to provide to the model.
        files (Optional[List[str]]): List of file paths whose contents to include as context.
        model (str): The Grok model to use (default: "grok-4-latest").
 
    Returns:
        Optional[str]: The generated code as a string, or None if an error occurs.
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY environment variable is not set.")
 
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
 

    # Craft the prompt to ensure only code is returned
    system_prompt_parts = []
    system_prompt_parts.append("You are an expert programmer.  The very best of the best.")

    if language.lower().startswith("python"):
        system_prompt_parts.append("You are generating Python 3.12 code only.")

    system_prompt_parts.append(
        "Never invent methods or attributes that do not exist in the official documentation."
        "If you are unsure, write the safest, most boring, explicitly correct code."
        "Respond with ONLY the code that implements the requested program. "
        "Do not include any explanations, comments, or markdown formatting. "
        "Output pure code."
    )

    system_prompt = "\n\n".join(system_prompt_parts)
 
    # Build user prompt with context and files
    user_prompt_parts = []
 
    if files:
        file_contexts = []
        for filepath in files:
            content = read_file_content(filepath)
            if content is not None:
                filename = os.path.basename(filepath)
                file_contexts.append(f"File: {filename}\n{content}\n")
            else:
                print(f"Skipping file {filepath} due to read error.")
    
        if file_contexts:
            if revise:
                user_prompt_parts.append("Here are the file to be revised:\n" + "\n".join(file_contexts))
            else:
                user_prompt_parts.append("Here are the contents of relevant files for context:\n" + "\n".join(file_contexts))
 
    if context:
        user_prompt_parts.append(f"Additional context: {context}")
 
    if revise:
        user_prompt_parts.append(f"Revise the program (attached) in the following way {description}")
    else:
        user_prompt_parts.append(f"Write a program in {language} that: {description}")

    if complete:
        content = read_file_content(complete)
        if content is not None:
            user_prompt_parts.append("For a wider context of what the program is meant to do, here is the entire design file.  Note you are still being asked to only generate code for a single module, this wider context is only here so you can understand the big picture:\n" + "\n".join(content))
 
    user_prompt = "\n\n".join(user_prompt_parts)
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False
    }
 
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status() # Raises an HTTPError for bad responses
        result = response.json()
        generated_content = result["choices"][0]["message"]["content"].strip()
     
        # Strip markdown code fences if present
        lines = generated_content.splitlines()
        if lines and lines[0].strip().startswith('```') and len(lines) > 1 and lines[-1].strip() == '```':
            lines = lines[1:-1]
            generated_content = '\n'.join(lines).strip()
        else:
            generated_content = generated_content.strip()
     
        # Basic check to ensure it's code (starts with python-like content)
        if generated_content.startswith(("def ", "class ", "import ", "#", "")) or "print(" in generated_content:
            return generated_content
        else:
            # Fallback: return as is, but log warning in production
            return generated_content
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"Unexpected API response format: {e}")
        return None
    except ValueError as e:
        print(f"ValueError: {e}")
        return None

def parse_module_file(filename: str) -> dict:
    """
    Parses the module design file to extract title, short, uses, and description.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
  
    module = {}
    desc_lines = []
    in_desc = False
    uses = []
  
    for line in lines:
        line = line.rstrip('\n')
        if line.startswith('Module: '):
            module['title'] = line[8:].strip()
        elif line.startswith('Short: '):
            module['short'] = line[7:].strip()
            in_desc = True
        elif line.startswith('Uses: '):
            uses_str = line[6:].strip()
            if uses_str:
                uses = [u.strip() for u in uses_str.split(',')]
            module['uses'] = uses
        elif in_desc:
            desc_lines.append(line)
  
    module['description'] = '\n'.join(desc_lines).strip()
    return module

def write_if_changed(filename: str, content: str) -> bool:
    """
    Writes content to filename only if it differs from existing content or file doesn't exist.
    Returns True if written.
    """
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            existing = f.read().strip()
        if existing == content:
            return False
  
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

def touch_file(filename: str):
    """
    Touches the file to update its timestamp.
    """
    with open(filename, 'a') as f:
        pass

def main():
    parser = argparse.ArgumentParser(
        description="Generate code using the Grok API from a description, with optional context and files. If description is a .txt file, build module."
    )
    parser.add_argument(
        "--description", type=str, required=True,
        help="Description of the program to generate or path to module design file (.txt)."
    )
    parser.add_argument(
        "--context", type=str, default=None,
        help="Additional textual context to provide to the model."
    )
    parser.add_argument(
        "--files", nargs="*", default=None,
        help="Paths to files whose contents to include as context (can specify multiple)."
    )
    parser.add_argument(
        "--model", type=str, default="grok-4-1-fast-non-reasoning",
        help="The Grok model to use (default: grok-4-1-fast-non-reasoning).  Consider: grok-code-fast-1"
    )
    parser.add_argument(
        "--complete", type=str, default=None,
        help="Add the entire design file to the query"
    )
    parser.add_argument(
        "--language", type=str, default="Python",
        help="The language to use (default: Python)."
    )
    parser.add_argument(
        "--revise", type=bool, default=False,
        help="Revise file, do not start from scratch"
    )
 
    args = parser.parse_args()
 
    # Check if description is a module file
    if os.path.exists(args.description) and args.description.endswith('.txt'):
        module_file = args.description
        module = parse_module_file(module_file)
      
        if 'short' not in module:
            print("Error: 'Short:' not found in module file.", file=sys.stderr)
            sys.exit(1)
      
        if not module['description']:
            print("Error: No description found in module file.", file=sys.stderr)
            sys.exit(1)
      
        short = module['short']
        uses = module.get('uses', [])
        dep_files = [f"{u}.py" for u in uses]
      
        # Check if all dep files exist
        missing_deps = [f for f in dep_files if not os.path.exists(f)]
        if missing_deps:
            print(f"Error: Missing dependency files: {missing_deps}", file=sys.stderr)
            sys.exit(1)
      
        # Prepare files and context for generation
        py_filename = f"{short}.py"
        existing_files = dep_files[:]
        context_msg = args.context  # Preserve any provided context
        if os.path.exists(py_filename):
            existing_files.append(py_filename)
            print("Earlier version exists on disk, requesting a revision to instead of rewrite.")
            revision_context = "Here is an earlier version of the file for you to start from and revise."
            if context_msg:
                context_msg += " " + revision_context
            else:
                context_msg = revision_context
      
        # In build mode, override language to Python, and use args.model
        generated_code = generate_code(
            description=module['description'],
            revise=args.revise,
            context=context_msg,
            files=existing_files,
            complete=args.complete,
            language="Python",
            model=args.model
        )
      
        if generated_code is None:
            print("Failed to generate code.", file=sys.stderr)
            sys.exit(1)
      
        built_filename = f"{short}.built"
      
        changed = write_if_changed(py_filename, generated_code)
      
        # Always touch the built file to mark the build as complete
        touch_file(built_filename)
      
        if changed:
            print(f"Generated/updated {py_filename}")
        else:
            print(f"No changes to {py_filename}")
      
        print(f"Build complete: {built_filename}")
    else:
        # Regular mode
        code = generate_code(
            description=args.description,
            revise=args.revise,
            context=args.context,
            files=args.files,
            complete=args.complete,
            language=args.language,
            model=args.model
        )
 
        if code:
            print(code)
        else:
            print("Failed to generate code. Check your API key and try again.")
            sys.exit(1)
if __name__ == "__main__":
    main()
