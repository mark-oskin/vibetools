#!/usr/bin/python3
import os
import sys
import subprocess
import readline
import glob
import re
import signal
import atexit
from pathlib import Path
import shlex

env = {}
env['prompt'] = '$ '
env['PWD'] = os.getcwd()
env['HOME'] = os.environ.get('HOME', str(Path.home()))
env['OLDPWD'] = ''
path_str = os.environ.get('PATH', '/bin:/usr/bin:/usr/sbin:.')
env['path'] = path_str.split(':')
history = []
job_counter = 0
bg_jobs = []
histfile = Path.home() / '.psh_history'

def default_prompt():
    return f"{os.path.basename(env['PWD']) or '/'} $ "

env['prompt'] = default_prompt

def get_prompt():
    p = env.get('prompt', '$ ')
    if callable(p):
        return p()
    return p

def expand_arg(arg):
    arg = os.path.expanduser(arg)
    def repl(m):
        return str(env.get(m.group(1), ''))
    arg = re.sub(r'\$([a-zA-Z_]\w*)', repl, arg)
    return arg

def glob_args(args):
    new_args = []
    for arg in args:
        gs = glob.glob(arg)
        if gs:
            new_args.extend(gs)
        else:
            new_args.append(arg)
    return new_args

def execute_cd(first_part):
    parts = shlex.split(first_part)
    arg = ''
    if len(parts) > 1:
        arg = expand_arg(parts[1])
    if arg == '-':
        oldpwd = env.get('OLDPWD', '')
        if oldpwd:
            print(oldpwd)
            os.chdir(oldpwd)
            env['PWD'] = os.getcwd()
            return
        else:
            print('cd: OLDPWD not set')
            return
    try:
        old = os.getcwd()
        os.chdir(arg)
        env['OLDPWD'] = old
        env['PWD'] = os.getcwd()
    except FileNotFoundError:
        print(f"cd: no such file or directory: {arg}")
    except PermissionError:
        print(f"cd: Permission denied: {arg}")
    except Exception as e:
        print(f"cd: {e}")

def execute_pwd():
    print(os.getcwd())

def execute_exit(first_part):
    parts = shlex.split(first_part)
    code = 0
    if len(parts) > 1:
        try:
            code = int(parts[1])
        except ValueError:
            code = 0
    sys.exit(code)

def execute_echo(first_part):
    parts = shlex.split(first_part)
    args = parts[1:]
    no_nl = False
    if args and args[0] == '-n':
        no_nl = True
        args = args[1:]
    for i, arg in enumerate(args):
        args[i] = expand_arg(arg)
    msg = ' '.join(args)
    print(msg, end='' if no_nl else '\n')

def execute_jobs():
    global bg_jobs
    for jid, pid, cmd in bg_jobs[:]:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            bg_jobs.remove((jid, pid, cmd))
    if not bg_jobs:
        print('No jobs')
        return
    for jid, pid, cmd in bg_jobs:
        print(f'[{jid}]  Running    {pid}   {cmd}')

def is_builtin(cmd):
    return cmd in ['cd', 'pwd', 'exit', 'echo', 'jobs']

def parse_command(command):
    parts = [p.strip() for p in command.split('|')]
    pipeline = []
    for part in parts:
        tokens = shlex.split(part)
        cmd_args = []
        redirects = {}
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in ['>', '>>', '<', '2>', '2>>']:
                op = tok
                i += 1
                if i < len(tokens):
                    file = expand_arg(tokens[i])
                    if op == '>':
                        redirects['stdout'] = ('w', file)
                    elif op == '>>':
                        redirects['stdout'] = ('a', file)
                    elif op == '<':
                        redirects['stdin'] = file
                    elif op == '2>':
                        redirects['stderr'] = ('w', file)
                    elif op == '2>>':
                        redirects['stderr'] = ('a', file)
                i += 1
            else:
                expanded = expand_arg(tok)
                cmd_args.append(expanded)
                i += 1
        pipeline.append((cmd_args, redirects))
    return pipeline

def find_command(cmd):
    cmd_path = None
    if '/' in cmd or cmd.startswith('.'):
        if os.path.isfile(cmd) and os.access(cmd, os.X_OK):
            cmd_path = cmd
    else:
        for p in env['path']:
            candidate = os.path.join(p, cmd)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                cmd_path = candidate
                break
        if not cmd_path:
            py_candidate = f"{cmd}.py"
            for p in [os.getcwd()] + env['path']:
                candidate = os.path.join(p, py_candidate)
                if os.path.isfile(candidate):
                    return f"/usr/bin/python3 {candidate}"
    return cmd_path

def execute_pipeline(pipeline, background=False, cmd_str=''):
    if not pipeline:
        return []
    processes = []
    prev_stdout = None
    for i, (cmd_args, redirects) in enumerate(pipeline):
        if not cmd_args:
            continue
        cmd_args = glob_args(cmd_args)
        cmd = cmd_args[0]
        cmd_path = find_command(cmd)
        if not cmd_path:
            print(f"{cmd}: command not found")
            return processes
        
        if cmd_path.startswith('/usr/bin/python3 '):
            args = cmd_path.split()
        else:
            args = cmd_args[:]
            args[0] = cmd_path

        stdin = prev_stdout
        stdout = subprocess.PIPE if i < len(pipeline) - 1 else None
        stderr = None

        if 'stdin' in redirects:
            try:
                stdin = open(redirects['stdin'], 'r')
            except Exception as e:
                print(f"Error opening stdin: {e}")
                stdin = None
        if 'stdout' in redirects:
            mode, file_ = redirects['stdout']
            try:
                stdout = open(file_, mode)
            except Exception as e:
                print(f"Error opening stdout: {e}")
                stdout = None
        if 'stderr' in redirects:
            mode, file_ = redirects['stderr']
            try:
                stderr = open(file_, mode)
            except Exception as e:
                print(f"Error opening stderr: {e}")
                stderr = None

        try:
            proc = subprocess.Popen(args, stdin=stdin, stdout=stdout, stderr=stderr,
                                    universal_newlines=False)
            processes.append(proc)
            if stdin and stdin != subprocess.PIPE and stdin != prev_stdout:
                pass
            prev_stdout = proc.stdout if stdout == subprocess.PIPE else None
        except Exception as e:
            print(f"Error: {e}")
            return processes

    if background:
        global job_counter, bg_jobs
        job_counter += 1
        pid_str = processes[0].pid if processes else '?'
        print(f'[{job_counter}] {pid_str}')
        bg_jobs.append((job_counter, processes[0].pid if processes else 0, cmd_str[:40]))
        return processes
    else:
        for proc in processes:
            proc.wait()
        return processes

def execute_line(line):
    commands = [c.strip() for c in line.split(';')]
    for command in commands:
        if not command:
            continue
        background = False
        if command.endswith('&'):
            background = True
            command = command[:-1].strip()
        first_part = command.split('|')[0].strip()
        if not first_part:
            continue
        try:
            parts = shlex.split(first_part)
            builtin_cmd = parts[0]
        except:
            builtin_cmd = ''
        if is_builtin(builtin_cmd):
            if builtin_cmd == 'cd':
                execute_cd(first_part)
            elif builtin_cmd == 'pwd':
                execute_pwd()
            elif builtin_cmd == 'exit':
                execute_exit(first_part)
            elif builtin_cmd == 'echo':
                execute_echo(first_part)
            elif builtin_cmd == 'jobs':
                execute_jobs()
            continue
        pipeline = parse_command(command)
        execute_pipeline(pipeline, background, command)

def completer(text, state):
    if state == 0:
        matches = []
        builtins_list = ['cd', 'pwd', 'exit', 'echo', 'jobs', 'history', 'source']
        matches.extend([b for b in builtins_list if b.startswith(text)])
        for p in env['path']:
            try:
                exes = [f for f in os.listdir(p)
                        if f.startswith(text) and os.access(os.path.join(p, f), os.X_OK)]
                matches.extend(exes)
            except (PermissionError, FileNotFoundError):
                pass
        is_path_like = '/' in text or text.startswith('~')
        if not is_path_like:
            try:
                files = [f for f in os.listdir('.')
                         if f.startswith(text)]
                matches.extend(files)
            except (PermissionError, FileNotFoundError):
                pass
        if is_path_like:
            head = os.path.dirname(os.path.expanduser(text)) or '.'
            tail = os.path.basename(text)
            try:
                files = [f for f in os.listdir(head)
                         if f.startswith(tail)]
                matches = [os.path.join(head, f) for f in files]
            except (PermissionError, FileNotFoundError):
                pass
        matches = sorted(set(matches))
        completer.matches = matches
    try:
        return completer.matches[state]
    except AttributeError:
        return None
    except IndexError:
        return None

readline.set_completer(completer)
readline.parse_and_bind('tab: complete')

try:
    readline.read_history_file(histfile)
    hlen = readline.get_current_history_length()
    history[:] = [readline.get_history_item(i) for i in range(1, hlen + 1)]
except:
    pass

def save_history():
    try:
        readline.set_history_length(1000)
        readline.write_history_file(histfile)
    except:
        pass

atexit.register(save_history)

while True:
    full_line = ''
    first_prompt = True
    while True:
        try:
            if first_prompt:
                prompt_str = get_prompt()
                first_prompt = False
            else:
                prompt_str = '> '
            inp = input(prompt_str)
        except KeyboardInterrupt:
            print()
            full_line = ''
            first_prompt = True
            break
        except EOFError:
            print()
            save_history()
            sys.exit(0)
        full_line += inp
        if not inp.endswith('\\'):
            break
        full_line = full_line[:-1]
    if not full_line.strip():
        continue
    line = full_line.strip()
    history.append(line)
    readline.add_history(line)
    if line == 'help':
        print("""This is a custom shell based on bash-like syntax.

Supported features:
- Command execution with path search, pipes (|), redirections (>, >>, <, 2>, 2>>)
- Sequences (;), background jobs (&) with job numbers
- Environment variables via env dict, e.g., (env['var'] = 'value'), $var expansion
- Inline Python code in ( ) with exception handling
- Multi-line input with \\ at end of lines, PS2 prompt
- source filename: execute Python file internally
- Tab completion for builtins, commands, files, paths
- Command history with up/down arrows, !n, history
- jobs: list background jobs
- Builtins: cd [-], pwd, exit [n], echo [-n], jobs
- Glob expansion (* ? [])
- ~ expansion
- Dynamic prompt via env['prompt'] = lambda: ...
""")
        continue
    if line == 'history':
        for i, h in enumerate(history):
            print(f"{i+1}: {h}")
        continue
    if line.startswith('!'):
        try:
            n = int(line[1:])
            if 1 <= n <= len(history):
                line = history[n-1]
            else:
                print("Invalid history number")
                continue
        except ValueError:
            print("Invalid history number")
            continue
    if line.startswith('(') and line.endswith(')'):
        code = line[1:-1]
        try:
            exec(code, {'env': env, '__builtins__': __builtins__})
        except Exception as e:
            print(f"Error: {e}")
        continue
    parts = line.split()
    if parts and parts[0] == 'source':
        if len(parts) > 1:
            filename = expand_arg(parts[1])
            if os.path.exists(filename):
                try:
                    with open(filename) as f:
                        code = f.read()
                    exec(code, {'env': env, '__builtins__': __builtins__})
                except Exception as e:
                    print(f"Error: {e}")
            else:
                print("File not found")
        else:
            print("Usage: source filename")
        continue
    execute_line(line)
