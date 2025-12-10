#!/usr/bin/python3
import argparse
import os
import requests
import subprocess
import shlex
import re
import json

def execute_program(command, stdin_input, timeout=30):
    """
    Executes a program with the given command and piped stdin_input.
    Captures stdout and stderr, combines them.
   
    Returns (True, combined_output) if the program exits normally (returncode 0)
    or is terminated after timeout seconds.
    Returns (False, combined_output) if the program fails (non-zero returncode).
   
    :param command: List of strings, e.g., ['ls', '-l']
    :param stdin_input: String to pipe into stdin
    :param timeout: Timeout in seconds (default 30)
    :return: Tuple (bool success, str output)
    """
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=0 # Unbuffered
        )
        stdout, stderr = proc.communicate(input=stdin_input, timeout=timeout)
       
        # Check returncode after normal completion
        if proc.returncode == 0:
            return True, stdout + stderr
        else:
            return False, stdout + stderr
           
    except subprocess.TimeoutExpired:
        # Process was killed due to timeout; partial output is available
        # In Python 3.3+, communicate() with timeout provides partial stdout/stderr
        # and proc.returncode is set (e.g., to -SIGTERM)
        return True, stdout + stderr
    except Exception as e:
        # Handle unexpected errors (e.g., command not found)
        return False, f"Error executing command: {str(e)}"

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
    parser = argparse.ArgumentParser(description="Debug a program using Grok API.")
    parser.add_argument('--files', nargs='+', required=True, help="List of files to include for debugging")
    parser.add_argument('--input_files', nargs='+', required=True, help="List of input files for debugging")
    parser.add_argument('--command', type=str, required=True, help="Command  execute the program (as string)")
    parser.add_argument('--input', type=str, required=True, help="Input string to pipe to stdin")
    parser.add_argument('--max_iterations', type=int, default=5, help="Maximum number of debugging iterations")
    parser.add_argument('--model', type=str, default="grok-4-1-fast-non-reasoning", help="Model to use for API calls")
    parser.add_argument('--issue', type=str, default=None, help="Describe the problem and pass that to grok, don't execute")
    args = parser.parse_args()

    # Parse command string into list
    command_list = shlex.split(args.command)

    api_key = os.getenv('XAI_API_KEY')
    if not api_key:
        print("Error: XAI_API_KEY environment variable not set.")
        return

    success = False
    for iteration in range(args.max_iterations):
        print(f"\n--- Iteration {iteration + 1} ---")
        if args.issue:
            success_flag, output = execute_program(command_list, args.input)
            success_flag = False
            output = ""
        else:
            success_flag, output = execute_program(command_list, args.input)
            print(f"Execution {'succeeded' if success_flag else 'failed'}")
            print("Output:", output if output else "No output")
        
        if success_flag:
            print("Program executed successfully!")
            success = True
            break
        else:
            # Read current files
            files_dict = read_files(args.files)
            
            # Prompt for Grok
            files_formatted = format_files_for_prompt(files_dict)

            if args.input_files:
                input_files_dict = read_files(args.input_files)
                input_files_formatted = format_files_for_prompt(input_files_dict)

            if args.issue:
                prompt_part = f"The program is failing in the following way: {args.issue} and for reference here is (stdout + stderr) of execution: {output}"
            else:
                prompt_part = f"The program failed with this output (stdout + stderr): {output}"
    
            prompt = f"""You are an expert code debugger. Here are the source files to debug:

{files_formatted}

The command to run the program is: {args.command}

The input piped to stdin is: {args.input}
{prompt_part}

Here are the input files the program reads (if any, this may be blank):
{input_files_formatted}

Your task: Debug and fix the code in the provided files so that it executes successfully (return code 0) with the given command and input. Make minimal changes. Preserve the file structure and only modify the necessary parts.

Respond ONLY with the fixed files, each in the exact format below (no other text or explanations):

File: filename.ext
```
fixed content here
```

Repeat for each file, even if unchanged. Do not add extra lines or markdown outside these blocks."""

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
                # Parse fixed files
                fixed_files = parse_fixed_files(content)
                print(f"Parsed {len(fixed_files)} fixed files")
                if not fixed_files:
                    raise ValueError("No fixed files parsed from response")
                # Write back
                write_fixed_files(fixed_files)
                if args.issue:
                    break
                print("Files updated by Grok. Retrying...")
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
                print(f"API request failed: {{re}}")
                print("Aborting debugging.")
                break
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error processing API response: {{e}}")
                # Optionally, save raw response for debugging
                try:
                    with open('debug_response.txt', 'w') as f:
                        f.write(response.text)
                    print("Raw response saved to debug_response.txt for inspection.")
                except NameError:
                    pass  # No response object
                print("Aborting debugging.")
                break
            except Exception as e:
                print(f"Unexpected error: {{e}}")
                print("Aborting debugging.")
                break
    if not success:
        print("\nMax iterations reached or error occurred. Program still failing.")

if __name__ == "__main__":
    main()
