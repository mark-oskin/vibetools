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
        formatted += f"File: {filename}\n\n{content}\n\n\n"
    return formatted

def main():
    parser = argparse.ArgumentParser(description="Bundle multiple source files into one.")
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
You are an expert software engineer.  You've been asked to organize the
code in a collection of source files so that they are in one single source file,
with the code appearing in a logical order.  Response only with the the combined
single source file, no other commentary.

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
        response = requests.post(url, headers=headers, json=data, timeout=240)
        response.raise_for_status()
        resp_json = response.json()

        generated_content = resp_json["choices"][0]["message"]["content"].strip()
     
        # Strip markdown code fences if present
        lines = generated_content.splitlines()
        if lines and lines[0].strip().startswith('```') and len(lines) > 1 and lines[-1].strip() == '```':
            lines = lines[1:-1]
            generated_content = '\n'.join(lines).strip()
        else:
            generated_content = generated_content.strip()
     

        print(generated_content)
    except requests.exceptions.HTTPError as he:
        if response.status_code == 404:
            print(f"404 error likely due to invalid model '{args.model}'. Valid models: grok-4-1-fast-reasoning, grok-4-1-fast-non-reasoning, grok-4-fast-reasoning, grok-4-fast-non-reasoning, grok-code-fast-1, grok-4")
            print("Response body:", response.text)
        else:
            print(f"API request failed: {{he}}")
            print("Response body:", response.text)
        print("Aborting  bundle.")
    except requests.exceptions.Timeout:
        print("API request timed out.")
        print("Aborting  bundle.")
    except requests.exceptions.RequestException as re:
        print(f"API request failed: {re}")
        print("Aborting  bundle.")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error processing API response: {e}")
        # Optionally, save raw response for debugging
        try:
            with open('debug_response.txt', 'w') as f:
                f.write(response.text)
            print("Raw response saved to debug_response.txt for inspection.")
        except NameError:
            pass  # No response object
        print("Aborting bundle.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("Aborting reverse.")

if __name__ == "__main__":
    main()
