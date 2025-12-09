#!/usr/bin/python3
import argparse
import os
import requests
import subprocess
import shlex
import re
import json

def read_files(files):
    """Read the contents of the files into a dictionary {filename: content}."""
    contents = {}
    for f in files:
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as file:
                contents[f] = file.read()
        else:
            print(f"Warning: File {f} does not exist.")
            contents[f] = ""  # Empty if missing
    return contents

def format_files_for_prompt(files_dict):
    """Format files as code blocks for the prompt."""
    formatted = ""
    for filename, content in files_dict.items():
        print(f"File: {filename}")
        formatted += f"File: {filename}\n\n{content}\n\n\n"
    return formatted

def main():
    parser = argparse.ArgumentParser(description="Reverse engineer a design document from code.")
    parser.add_argument('--files', nargs='+', required=True, help="List of source files")
    parser.add_argument('--model', type=str, default="grok-4-1-fast-non-reasoning", help="Model to use for API calls")
    parser.add_argument(
        "--language", type=str, default="Python3.12",
        help="Assume the design document is for a program written in a given language."
    )
    args = parser.parse_args()

    api_key = os.getenv('XAI_API_KEY')
    if not api_key:
        print("Error: XAI_API_KEY environment variable not set.")
        return

    # Read current files
    files_dict = read_files(args.files)
    
    # Prompt for Grok
    files_formatted = format_files_for_prompt(files_dict)

    prompt = f"""
You are an expert software engineer and program desiner.  Your job is write a design document
for a collection of existing source files.  The design document needs to be a veyr specific
stylized format, described below:

These design documents consist of a description of different modules.
Each module starts with a line by itself 'Module: ' followed by a
human readable name for that module that describes what it does.
Next a line should be 'Short: ' followed by a computer readable name
for that module that is unique both to the program and from any standard
library import or include.  This computer name will be used as the source file name
for that module.  Finally if that module depends on any other modules
in the design document another line should be added next 'Uses: ' which
followed by a comma separated list of short names that the module depends on.
        
Note that it is important modules are dependent on each other in a strict
tree like structure.  There can be no circular dependencies.  If you want
to make such a circular dependecy, then the modules should be merged into
one.

Modules should be described in the file from top level to bottom level.
Meaning the first module should be the top level source of the program,
sometimes referred to as the main.  From there modules it depends on
should be described.

Short module names should never use the same name as standard library
for import or include names that are part of the main {args.language} standard.

After these stylized lines an English language description for what that
module should do should follow.  This should be well organized, describing
what the module does, possibly some of the ways it will do it, possibly 
example inputs and outputs, and possibly even function names or types"
that module will export for other modules to use.
It is helpful that this textural description be formatted for a human to
read.  Meaning, it has paragraphs, lists, etc.   Ultimately you (grok)
will read it too, but a human may edit it before that happens.

Any globally visible type, variable or function names described in the document
should be unique across all modules and distinct from any standard language
supported library function, class, type or variable names.

Respond only with the design document, without any other commentary.  The number
of modules in the design document should be equivalent to the number of files provided.
The linkages between modules (the Uses: clause) should be correct and follow the
dependencies across modules. 

Here are the source files to work on.  Note that the source files may not be
the same language that the design document is targetting.

{files_formatted}

"""
    try:
        url = "https://api.x.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        print(f"Sending request with model: {args.model}")  # Debug info
        response = requests.post(url, headers=headers, json=data, timeout=240)
        response.raise_for_status()
        resp_json = response.json()
        content = resp_json["choices"][0]["message"]["content"]
        print(f"API response length: {len(content)} characters")
        print(content)
    except requests.exceptions.HTTPError as he:
        if response.status_code == 404:
            print(f"404 error likely due to invalid model '{args.model}'. Valid models: grok-4-1-fast-reasoning, grok-4-1-fast-non-reasoning, grok-4-fast-reasoning, grok-4-fast-non-reasoning, grok-code-fast-1, grok-4")
            print("Response body:", response.text)
        else:
            print(f"API request failed: {{he}}")
            print("Response body:", response.text)
        print("Aborting debugging.")
    except requests.exceptions.Timeout:
        print("API request timed out.")
        print("Aborting debugging.")
    except requests.exceptions.RequestException as re:
        print(f"API request failed: {re}")
        print("Aborting debugging.")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error processing API response: {e}")
        # Optionally, save raw response for debugging
        try:
            with open('debug_response.txt', 'w') as f:
                f.write(response.text)
            print("Raw response saved to debug_response.txt for inspection.")
        except NameError:
            pass  # No response object
        print("Aborting reverse.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("Aborting reverse.")

if __name__ == "__main__":
    main()
