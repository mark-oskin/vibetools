#!/usr/bin/python3
"""
A Python module to generate code using the Grok API from xAI.
Requires the XAI_API_KEY environment variable to be set.
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

def generate_design_document(description: str,
                  context: Optional[str] = None,
                  files: Optional[List[str]] = None,
                  language: str = "Python3",
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
    system_prompt = (
        "You are a helpful program manager for a software development company."
        "Your job is to edit and/or create design documents for different types of programs."
        f"Your company writes code in {language}."
        "These design documents consist of a description of different modules."
        "Each module starts with a line by itself 'Module: ' followed by a"
        "human readable name for that module that describes what it does."
        "Next a line should be 'Short: ' followed by a computer readable name"
        "for that module that is unique both to the program and from any standard"
        "library import or include.  This computer name will be used as the source file name"
        "for that module.  Finally if that module depends on any other modules"
        "in the design document another line should be added next 'Uses: ' which"
        "followed by a comma separated list of short names that the module depends on."
        ""
        "Note that it is important modules are dependent on each other in a strict"
        "tree like structure.  There can be no circular dependencies.  If you want"
        "to make such a circular dependecy, then the modules should be merged into"
        "one."
        ""
        "Modules should be described in the file from top level to bottom level."
        "Meaning the first module should be the top level source of the program,"
        "sometimes referred to as the main.  From there modules it depends on"
        "should be described."
        ""
        "Short module names should never use the same name as standard library"
        f"or import or include names that are part of the main {language} standard."
        ""
        "After these stylized lines an English language description for what that"
        "module should do should follow.  This should be well organized, describing"
        "what the module does, possibly some of the ways it will do it, possibly "
        "example inputs and outputs, and possibly even function names or types"
        "that module will export for other modules to use."
        "It is helpful that this textural description be formatted for a human to"
        "read.  Meaning, it has paragraphs, lists, etc.   Ultimately you (grok)"
        "will read it too, but a human may edit it before that happens."
        ""
        "Any globally visible type, variable or function names described in the document"
        "should be unique across all modules and distinct from any standard language"
        "supported library function, class, type or variable names."
        ""
        "Respond only with the design document, without any other commentary."
    )
 
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
            user_prompt_parts.append("Here are the contents of relevant files for context:\n" + "\n".join(file_contexts))
 
    if context:
        user_prompt_parts.append(f"Additional context: {context}")
 
    user_prompt_parts.append(f"Write a design document for program that: {description}")
 
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
        description="Generate or refine design documents using the Grok API"
    )
    parser.add_argument(
        "--description", type=str, required=True,
        help="Description of the program to generate"
    )
    parser.add_argument(
        "--language", type=str, default="Python3.12",
        help="Assume the design document is for a program written in a given language."
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
        "--model", type=str, default="grok-4-1-fast-reasoning",
        help="The Grok model to use (default: grok-4-1-fast-reasoning)"
    )
  
    args = parser.parse_args()
 
    # Regular mode
    design_document = generate_design_document(
        description=args.description,
        context=args.context,
        files=args.files,
        language=args.language,
        model=args.model
    )

    if design_document:
        print(design_document)
    else:
        print("Failed to generate design document. Check your API key and try again.")
        sys.exit(1)
if __name__ == "__main__":
    main()
