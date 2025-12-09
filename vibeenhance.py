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
        formatted += f"File: {filename}\n```\n{content}\n```\n\n"
    return formatted

def parse_fixed_files(content):
    """Parse the API response to extract fixed file contents.
    Assumes format: File: filename\n```\ncontent\n```
    Returns dict {filename: fixed_content}
    """
    files = {}
    # Find all blocks
    pattern = r'File:\s*([^\n]+?)\s*```\s*(.*?)```'
    matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)
    for filename, fixed_content in matches:
        filename = filename.strip()
        fixed_content = fixed_content.strip()
        files[filename] = fixed_content
    return files

def write_fixed_files(files_dict):
    """Write the fixed contents back to files, overwriting."""
    for filename, content in files_dict.items():
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Updated {filename}")

def main():
    parser = argparse.ArgumentParser(description="Enhance a program using Grok API.")
    parser.add_argument('--files', nargs='+', required=True, help="List of files to include for debugging")
    parser.add_argument('--max_iterations', type=int, default=1, help="Maximum number of iterations")
    parser.add_argument('--model', type=str, default="grok-4-1-fast-non-reasoning", help="Model to use for API calls")
    parser.add_argument('--enhance', type=str, default="Analyze what code does and add new features to it that you think would be broadly useful.", help="Describe how the code should be changed.")
    parser.add_argument('--suggest_only', type=bool, default=False, help="Suggest changes only, do not actually make them.")
    args = parser.parse_args()

    api_key = os.getenv('XAI_API_KEY')
    if not api_key:
        print("Error: XAI_API_KEY environment variable not set.")
        return

    for iteration in range(args.max_iterations):
        print(f"\n--- Iteration {iteration + 1} ---")
        # Read current files
        files_dict = read_files(args.files)
        
        # Prompt for Grok
        files_formatted = format_files_for_prompt(files_dict)

        if not args.suggest_only:
            prompt = f"""
You are an expert software engineer.
Your task is to improve this source code as follows: {args.enhance}

Respond ONLY with the updated files, each in the exact format below (no other text or explanations):

File: filename.ext
```
file content here
```

Repeat for each changed file (with the correct filenames of course).
Do not add extra lines or markdown outside these blocks.

Here are the source files to work on:

{files_formatted}

"""
        else:
            prompt = f"""
You are an expert software engineer and product manager.
Your task is to develop a list of 25 suggested improvements to this application.

Respond only with a list, numbered 1-25 of short one sentence improvement ideas.  No other
text or other items should be included.

Here are the source files to work on:

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
            if args.suggest_only:
                print(content)
                break
            # Parse fixed files
            fixed_files = parse_fixed_files(content)
            print(f"Parsed {len(fixed_files)} updated files")
            if not fixed_files:
                raise ValueError("No updated files parsed from response")
            # Write back
            write_fixed_files(fixed_files)
            print("Files updated by Grok...")
        except requests.exceptions.HTTPError as he:
            if response.status_code == 404:
                print(f"404 error likely due to invalid model '{args.model}'. Valid models: grok-4-1-fast-reasoning, grok-4-1-fast-non-reasoning, grok-4-fast-reasoning, grok-4-fast-non-reasoning, grok-code-fast-1, grok-4")
                print("Response body:", response.text)
            else:
                print(f"API request failed: {{he}}")
                print("Response body:", response.text)
            print("Aborting debugging.")
            break
        except requests.exceptions.Timeout:
            print("API request timed out.")
            print("Aborting debugging.")
            break
        except requests.exceptions.RequestException as re:
            print(f"API request failed: {re}")
            print("Aborting debugging.")
            break
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error processing API response: {e}")
            # Optionally, save raw response for debugging
            try:
                with open('debug_response.txt', 'w') as f:
                    f.write(response.text)
                print("Raw response saved to debug_response.txt for inspection.")
            except NameError:
                pass  # No response object
            print("Aborting enhance.")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            print("Aborting enhance.")
            break

if __name__ == "__main__":
    main()
