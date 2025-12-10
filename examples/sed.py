from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator, List, Dict, Any, Optional, TypedDict, Union, Iterable
from enum import Enum
import sys
import re
import argparse
import os
import shutil
from pathlib import Path
from io import TextIOWrapper

class SedCommandType(Enum):
    BRANCH = 'b'
    COMMENT = '#'
    DELETE = 'd'
    DELETE_FIRST_LINE = 'D'
    EQUAL = '='
    GLOBAL_SUB = 'g'
    HOLD = 'h'
    HOLD_APPEND = 'H'
    INSERT = 'i'
    LABEL = ':'
    NEXT = 'n'
    NEXT_READ = 'N'
    PRINT = 'p'
    PRINT_FIRST_LINE = 'P'
    QUIT = 'q'
    QUIT_SILENT = 'Q'
    READ_FILE = 'r'
    READ_FILE_SILENT = 'R'
    SUBSTITUTE = 's'
    TEST = 't'
    TEST_BRANCH = 'T'
    EXCHANGE = 'x'
    TRANSLIT = 'y'
    WRITE = 'w'
    WRITE_FIRST_LINE = 'W'
    CHANGE = 'c'
    SWAPCASE = 'l'

@dataclass
class SedScript:
    commands: List[SedCommand] = field(default_factory=list)

SedCommand = TypedDict('SedCommand', {
    'addr1': Optional[Union[int, str]],
    'addr2': Optional[Union[int, str]],
    'cmd_type': SedCommandType,
    'args': Dict[str, Any]
})

class SedPatternSpace:
    def __init__(self):
        self.pattern_space: str = ''
        self.hold_space: str = ''
        self.substituted: bool = False
        self.line_num: int = 0
        self.last_line_num: int = 0

class RegexMatcher:
    def __init__(self, extended: bool = False):
        self.extended = extended
        self.patterns: Dict[str, re.Pattern] = {}
    
    def compile(self, pattern: str) -> re.Pattern:
        if pattern in self.patterns:
            return self.patterns[pattern]
        flags = re.MULTILINE
        if self.extended:
            flags |= re.VERBOSE
        regex = re.compile(pattern, flags)
        self.patterns[pattern] = regex
        return regex
    
    def match(self, pattern: str, string: str) -> re.Match | None:
        return self.compile(pattern).match(string)

class SedOptions:
    def __init__(self):
        self.quiet: bool = False
        self.extended_regex: bool = False
        self.in_place: Optional[str] = None
        self.unbuffered: bool = False
        self.null_data: bool = False
        self.sandbox: bool = False
        self.posix: bool = False
        self.separate: bool = False
        self.line_wrap: int = 80
        self.follow_symlinks: bool = False

def parse_address(addr: str, line_num: int, pattern_space: str, 
                 matcher: RegexMatcher, last_line_num: int) -> Optional[bool]:
    if addr is None:
        return None
    if isinstance(addr, int):
        return line_num == addr
    elif addr == '$':
        return line_num == last_line_num
    elif addr.startswith('/'):
        match = matcher.match(addr[1:-1], pattern_space)
        return bool(match)
    elif addr.isdigit():
        return line_num == int(addr)
    elif '~' in addr:
        start, step = map(int, addr.split('~'))
        return (line_num - start) % step == 0
    return None

def matches_command(ps: SedPatternSpace, cmd: SedCommand, 
                   matcher: RegexMatcher) -> bool:
    addr1_match = parse_address(cmd['addr1'], ps.line_num, ps.pattern_space, 
                               matcher, ps.last_line_num)
    addr2_match = parse_address(cmd['addr2'], ps.line_num, ps.pattern_space, 
                               matcher, ps.last_line_num)
    
    if cmd['addr1'] is None and cmd['addr2'] is None:
        return True
    if addr1_match is True:
        return True
    if addr1_match is False:
        return False
    if addr2_match is not None:
        return addr2_match
    return True

def execute_command(ps: SedPatternSpace, cmd: SedCommand, 
                   script: SedScript, options: SedOptions, 
                   labels: Dict[str, int], output: List[str], 
                   input_file: Optional[TextIOWrapper] = None) -> bool:
    if not matches_command(ps, cmd, RegexMatcher(options.extended_regex)):
        return True
    
    cmd_type = cmd['cmd_type']
    
    if cmd_type == SedCommandType.COMMENT:
        return True
    elif cmd_type == SedCommandType.LABEL:
        labels[cmd['args'].get('label', '')] = 0
        return True
    elif cmd_type == SedCommandType.BRANCH:
        label = cmd['args'].get('label', '0')
        if label in labels:
            return False
        return True
    elif cmd_type == SedCommandType.DELETE:
        ps.pattern_space = ''
        return False
    elif cmd_type == SedCommandType.DELETE_FIRST_LINE:
        if '\n' in ps.pattern_space:
            ps.pattern_space = ps.pattern_space.split('\n', 1)[1]
        else:
            ps.pattern_space = ''
        return False
    elif cmd_type == SedCommandType.PRINT:
        output.append(ps.pattern_space + '\n')
        return True
    elif cmd_type == SedCommandType.EQUAL:
        output.append(f"{ps.line_num}\n")
        return True
    elif cmd_type == SedCommandType.NEXT:
        return False
    elif cmd_type == SedCommandType.INSERT:
        output.append(cmd['args']['text'])
        return True
    elif cmd_type == SedCommandType.QUIT:
        return False
    elif cmd_type == SedCommandType.SUBSTITUTE:
        matcher = RegexMatcher(options.extended_regex)
        pat = cmd['args']['pattern']
        repl = cmd['args']['replacement']
        flags = cmd['args'].get('flags', '')
        global_flag = 'g' in flags
        
        count = cmd['args'].get('count', 0)
        if count > 0:
            result = matcher.compile(pat).sub(repl, ps.pattern_space, count)
            ps.substituted = result != ps.pattern_space
            ps.pattern_space = result
        else:
            count = 0 if global_flag else 1
            result = matcher.compile(pat).sub(repl, ps.pattern_space, count)
            ps.substituted = result != ps.pattern_space
            ps.pattern_space = result
        return True
    elif cmd_type == SedCommandType.HOLD:
        ps.hold_space = ps.pattern_space
        return True
    elif cmd_type == SedCommandType.HOLD_APPEND:
        ps.hold_space += '\n' + ps.pattern_space
        return True
    elif cmd_type == SedCommandType.EXCHANGE:
        ps.pattern_space, ps.hold_space = ps.hold_space, ps.pattern_space
        return True
    elif cmd_type == SedCommandType.TEST:
        if ps.substituted:
            return False
        return True
    elif cmd_type == SedCommandType.TEST_BRANCH:
        if not ps.substituted:
            return False
        return True
    
    return True

def PySedCore_parse_script(script_str_or_file: Union[str, Path], 
                          extended_regex: bool) -> SedScript:
    script = SedScript()
    if isinstance(script_str_or_file, Path):
        with open(script_str_or_file) as f:
            content = f.read()
    else:
        content = script_str_or_file
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        
        if not line or line.startswith('#'):
            cmd = SedCommand(addr1=None, addr2=None, cmd_type=SedCommandType.COMMENT, args={})
            script.commands.append(cmd)
            continue
        
        addr1, addr2, cmd_str = parse_addresses(line)
        
        if cmd_str.startswith(':'):
            cmd = SedCommand(addr1=addr1, addr2=addr2, 
                           cmd_type=SedCommandType.LABEL, 
                           args={'label': cmd_str[1:]})
        elif cmd_str.startswith('s'):
            cmd = parse_substitute(addr1, addr2, cmd_str)
        else:
            cmd_type = SedCommandType(cmd_str[0])
            cmd = SedCommand(addr1=addr1, addr2=addr2, cmd_type=cmd_type, args={})
        
        script.commands.append(cmd)
    
    return script

def parse_addresses(line: str) -> tuple[Optional[str], Optional[str], str]:
    addr1, addr2, cmd = None, None, line
    if ',' in line:
        parts = line.split(',', 1)
        addr1 = parts[0].strip()
        rest = parts[1]
        if ',' in rest:
            addr2, cmd = rest.split(',', 1)
            addr2, cmd = addr2.strip(), cmd.strip()
        else:
            addr2, cmd = None, rest.strip()
    elif line[0] in '0123456789/$':
        match = re.match(r'^(\d+|/[^/]+/|\$)(?:,(\d+|/[^/]+/|\$))?\s*([a-z])', line)
        if match:
            addr1, addr2, cmd_start = match.groups()
            cmd = line[match.end():].strip()
    return addr1, addr2, cmd

def parse_substitute(addr1: Optional[str], addr2: Optional[str], 
                    cmd_str: str) -> SedCommand:
    match = re.match(r's(/[^/]+/[^/]+/)(.*)', cmd_str)
    if match:
        pattern_repl, flags = match.groups()
        pattern, repl = pattern_repl[1:-1].split('/', 1)
        return SedCommand(addr1=addr1, addr2=addr2, 
                         cmd_type=SedCommandType.SUBSTITUTE,
                         args={'pattern': pattern, 'replacement': repl, 
                              'flags': flags})
    return SedCommand(addr1=addr1, addr2=addr2, 
                     cmd_type=SedCommandType.SUBSTITUTE, args={})

def PySedCore_process(input_streams: List[TextIOWrapper], 
                     script: SedScript, 
                     options: SedOptions) -> Iterator[str]:
    ps = SedPatternSpace()
    labels: Dict[str, int] = {}
    output_buffer: List[str] = []
    
    for stream in input_streams:
        ps.line_num = 0
        done = False
        
        while not done:
            if options.null_data:
                line = stream.read().rstrip('\0')
                if not line:
                    break
                ps.pattern_space = line + '\0'
            else:
                line = stream.readline()
                if not line:
                    break
                ps.pattern_space = line.rstrip('\n')
            
            ps.line_num += 1
            ps.last_line_num = ps.line_num
            
            continue_script = True
            cmd_idx = 0
            
            while continue_script and cmd_idx < len(script.commands):
                cmd = script.commands[cmd_idx]
                continue_script = execute_command(ps, cmd, script, options, 
                                                labels, output_buffer, stream)
                
                if cmd['cmd_type'] == SedCommandType.BRANCH:
                    label = cmd['args'].get('label', '0')
                    if label in labels:
                        cmd_idx = labels[label]
                    else:
                        cmd_idx += 1
                else:
                    cmd_idx += 1
            
            if not options.quiet:
                output_buffer.append(ps.pattern_space + '\n')
            
            if options.unbuffered:
                for line in output_buffer:
                    yield line
                output_buffer.clear()
        
        if options.separate:
            for line in output_buffer:
                yield line
            output_buffer.clear()
    
    for line in output_buffer:
        yield line

def backup_file(filepath: Path, suffix: str) -> None:
    backup_path = filepath.with_suffix(filepath.suffix + suffix)
    shutil.copy2(filepath, backup_path)

def process_in_place(input_file: Path, script: SedScript, options: SedOptions) -> None:
    with open(input_file, 'r') as infile:
        result = list(PySedCore_process([TextIOWrapper(infile.buffer, encoding='utf-8')], script, options))
    
    if options.in_place:
        backup_file(input_file, options.in_place)
    
    with open(input_file, 'w') as outfile:
        outfile.writelines(result)

def PySedCore_main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog='pysed', add_help=False)
    parser.add_argument('-n', '--quiet', action='store_true')
    parser.add_argument('-e', '--expression', dest='expressions', action='append')
    parser.add_argument('-f', '--file', dest='script_files', action='append')
    parser.add_argument('-i', dest='in_place', nargs='?', const='.bak')
    parser.add_argument('-E', '-r', '--regexp-extended', action='store_true')
    parser.add_argument('-z', '--null-data', action='store_true')
    parser.add_argument('-u', '--unbuffered', action='store_true')
    parser.add_argument('--sandbox', action='store_true')
    parser.add_argument('--posix', action='store_true')
    parser.add_argument('-s', '--separate', action='store_true')
    parser.add_argument('--follow-symlinks', action='store_true')
    
    args, remaining = parser.parse_known_args(argv[1:])
    
    options = SedOptions()
    options.quiet = args.quiet
    options.extended_regex = args.regexp_extended
    options.in_place = args.in_place
    options.unbuffered = args.unbuffered
    options.null_data = args.null_data
    options.sandbox = args.sandbox
    options.posix = args.posix
    options.separate = args.separate
    options.follow_symlinks = args.follow_symlinks
    
    script_strs = args.expressions or []
    script_files = getattr(args, 'script_files', []) or []
    
    if not script_strs and not script_files and remaining:
        script_strs = [remaining[0]]
        input_files = remaining[1:]
    else:
        input_files = remaining
    
    scripts = []
    for script_file in script_files:
        scripts.append(PySedCore_parse_script(Path(script_file), options.extended_regex))
    for script_str in script_strs:
        scripts.append(PySedCore_parse_script(script_str, options.extended_regex))
    
    if not scripts:
        print("pysed: no script provided", file=sys.stderr)
        return 1
    
    combined_script = scripts[0]
    
    streams: List[TextIOWrapper] = []
    if not input_files:
        streams.append(TextIOWrapper(sys.stdin.buffer, encoding='utf-8'))
    else:
        for fname in input_files:
            streams.append(TextIOWrapper(open(fname, 'rb'), encoding='utf-8'))
    
    try:
        if options.in_place and input_files:
            for fname in input_files:
                process_in_place(Path(fname), combined_script, options)
        else:
            for line in PySedCore_process(streams, combined_script, options):
                sys.stdout.write(line)
                sys.stdout.flush()
        
        return 0
    except Exception as e:
        print(f"pysed: error: {e}", file=sys.stderr)
        return 1
    finally:
        for stream in streams:
            if hasattr(stream, 'close') and stream != sys.stdin:
                stream.close()

PySedCore_main(sys.argv)