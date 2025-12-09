#!/usr/bin/python3
import argparse
import sys
import os
import stat
import time
import pwd
import grp
import shutil
from enum import Enum
from typing import List
from dataclasses import dataclass, field

class ColorMode(Enum):
    AUTO = 'auto'
    ALWAYS = 'always'
    NEVER = 'never'

class TimeMode(Enum):
    ATIME = 'atime'
    ACCESS = 'access'
    CTIME = 'ctime'
    USE = 'use'
    STATUS = 'status'
    MTIME = 'mtime'
    MODIFICATION = 'modification'

@dataclass(frozen=True)
class LsEntry:
    name: str
    full_path: str
    stat_result: os.stat_result
    is_dir: bool = field(init=False)
    is_symlink: bool = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'is_dir', bool(self.stat_result.st_mode & stat.S_IFDIR))
        object.__setattr__(self, 'is_symlink', bool(self.stat_result.st_mode & stat.S_IFLNK))

def entry_from_path(path: str, follow_symlinks: bool = False) -> LsEntry:
    if follow_symlinks:
        st = os.stat(path)
    else:
        st = os.lstat(path)
    return LsEntry(
        name=os.path.basename(path),
        full_path=path,
        stat_result=st
    )

def parse_arguments(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True, prog='ls')
    
    parser.add_argument('-a', '--all', dest='all', action='store_true',
                       help='do not ignore entries starting with .')
    parser.add_argument('-A', '--almost-all', dest='almost_all', action='store_true',
                       help='list all entries except . and ..')
    parser.add_argument('-B', '--ignore-backups', dest='ignore_backups', action='store_true',
                       help='ignore entries ending with ~')
    parser.add_argument('-b', '--escape', dest='escape', action='store_true',
                       help='escape non-printable characters')
    parser.add_argument('-C', dest='C', action='store_true',
                       help='multi-column output with vertical fill')
    parser.add_argument('-c', dest='c', action='store_true',
                       help='sort by ctime')
    parser.add_argument('-d', '--directory', dest='directory', action='store_true',
                       help='list directory entries themselves, not contents')
    parser.add_argument('-f', dest='f', action='store_true',
                       help='no sort, no filter')
    parser.add_argument('-F', '--classify', dest='classify', action='store_true',
                       help='append file type indicator to entries')
    parser.add_argument('-G', dest='no_color', action='store_true',
                       help='alias for --color=never')
    parser.add_argument('--human-readable', dest='human_readable', action='store_true',
                       help='print human readable sizes')
    parser.add_argument('-i', '--inode', dest='inode', action='store_true',
                       help='print inode number')
    parser.add_argument('-l', '--long-format', dest='long_format', action='store_true',
                       help='long listing format')
    parser.add_argument('-L', '--dereference', dest='dereference', action='store_true',
                       help='follow symlinks')
    parser.add_argument('-n', '--numeric-uid-gid', dest='numeric_uid_gid', action='store_true',
                       help='use numeric uid/gid')
    parser.add_argument('-1', dest='one_per_line', action='store_true',
                       help='one entry per line')
    parser.add_argument('-O', dest='omit_group', action='store_true',
                       help='omit group information')
    parser.add_argument('-p', dest='p', action='store_true',
                       help='append / to directories')
    parser.add_argument('-q', '--hide-control-chars', dest='hide_control_chars', action='store_true',
                       help='hide control characters')
    parser.add_argument('-R', '--recursive', dest='recursive', action='store_true',
                       help='list subdirectories recursively')
    parser.add_argument('-r', '--reverse', dest='reverse', action='store_true',
                       help='reverse sort order')
    parser.add_argument('-s', '--size', dest='size', action='store_true',
                       help='print size in blocks')
    parser.add_argument('-S', dest='S', action='store_true',
                       help='sort by size')
    parser.add_argument('-t', dest='t', action='store_true',
                       help='sort by modification time')
    parser.add_argument('-T', dest='full_time', action='store_true',
                       help='show full time')
    parser.add_argument('-u', dest='u', action='store_true',
                       help='sort by access time')
    parser.add_argument('-U', '--no-sort', dest='no_sort', action='store_true',
                       help='no sorting')
    parser.add_argument('-w', '--width', dest='width', type=int,
                       help='set output width')
    parser.add_argument('-x', dest='x', action='store_true',
                       help='multi-column output with horizontal rows')
    parser.add_argument('-X', '--sort', dest='sort_extension', action='store_true',
                       help='sort by extension')
    parser.add_argument('--color', dest='color', type=ColorMode, choices=list(ColorMode),
                       default=ColorMode.AUTO,
                       help='control color usage')
    parser.add_argument('--group-directories-first', dest='group_directories_first', action='store_true',
                       help='list directories first')
    parser.add_argument('--time', dest='time_style', type=TimeMode, choices=list(TimeMode),
                       default=TimeMode.MTIME,
                       help='specify time field to display')
    
    parser.add_argument('paths', nargs='*', default=['.'], metavar='path',
                       help='files/directories to list')
    
    try:
        return parser.parse_args(argv)
    except SystemExit:
        sys.exit(2)

def format_permissions(mode: int) -> str:
    type_char = {
        stat.S_IFIFO: 'p',
        stat.S_IFCHR: 'c',
        stat.S_IFDIR: 'd',
        stat.S_IFBLK: 'b',
        stat.S_IFREG: '-',
        stat.S_IFLNK: 'l',
        stat.S_IFSOCK: 's',
        stat.S_IFDOOR: 'D'
    }.get(stat.S_IFMT(mode), '?')
    
    perms = type_char
    perms += 'r' if mode & stat.S_IRUSR else '-'
    perms += 'w' if mode & stat.S_IWUSR else '-'
    user = ''
    if mode & stat.S_ISUID:
        user = 's' if mode & stat.S_IXUSR else 'S'
    else:
        user = 'x' if mode & stat.S_IXUSR else '-'
    perms += user
    
    perms += 'r' if mode & stat.S_IRGRP else '-'
    perms += 'w' if mode & stat.S_IWGRP else '-'
    group = ''
    if mode & stat.S_ISGID:
        group = 's' if mode & stat.S_IXGRP else 'S'
    else:
        group = 'x' if mode & stat.S_IXGRP else '-'
    perms += group
    
    perms += 'r' if mode & stat.S_IROTH else '-'
    perms += 'w' if mode & stat.S_IWOTH else '-'
    other = ''
    if mode & stat.S_ISVTX:
        other = 't' if mode & stat.S_IXOTH else 'T'
    else:
        other = 'x' if mode & stat.S_IXOTH else '-'
    perms += other
    
    return perms

def format_time(st: os.stat_result, options: argparse.Namespace) -> str:
    time_field = options.time_style.value if hasattr(options, 'time_style') else 'mtime'
    if options.full_time:
        fmt = '%Y-%m-%d %H:%M:%S.%f'[:-3]
        return time.strftime(fmt, time.localtime(getattr(st, f'st_{time_field}')))
    
    now = time.time()
    six_months_ago = now - 6 * 30 * 24 * 3600
    
    timestamp = getattr(st, f'st_{time_field}')
    if timestamp >= six_months_ago:
        fmt = '%b %d %H:%M'
    else:
        fmt = '%b %d  %Y'
    
    return time.strftime(fmt, time.localtime(timestamp))

def quote_name(name: str, quote_control: bool) -> str:
    if not quote_control:
        return name
    
    result = ''
    for c in name:
        if ord(c) < 32 or ord(c) > 126:
            result += f'?\\{ord(c):03o}'
        else:
            result += c
    return result

def classify_append(entry: LsEntry, options: argparse.Namespace) -> str:
    if not options.classify:
        return ''
    
    mode = entry.stat_result.st_mode
    if entry.is_dir:
        return '/'
    elif stat.S_ISLNK(mode):
        return '@'
    elif stat.S_ISREG(mode) and stat.S_IXUSR & mode:
        return '*'
    elif stat.S_ISFIFO(mode):
        return '|'
    elif stat.S_ISSOCK(mode):
        return '='
    return ''

def get_user_group(entry: LsEntry, options: argparse.Namespace) -> tuple[str, str]:
    if options.numeric_uid_gid:
        return str(entry.stat_result.st_uid), str(entry.stat_result.st_gid)
    
    try:
        user = pwd.getpwuid(entry.stat_result.st_uid).pw_name
    except KeyError:
        user = str(entry.stat_result.st_uid)
    
    try:
        group = grp.getgrgid(entry.stat_result.st_gid).gr_name
    except KeyError:
        group = str(entry.stat_result.st_gid)
    
    if options.omit_group:
        group = ''
    
    return user, group

def format_size(size: int, human: bool) -> str:
    if not human:
        return f"{size}"
    
    suffixes = ['', 'KiB', 'MiB', 'GiB', 'TiB']
    i = 0
    while size >= 1024 and i < len(suffixes) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f}{suffixes[i]}" if i > 0 else f"{size}{suffixes[i]}"

def format_entries(entries: list[LsEntry], options: argparse.Namespace, term_width: int, color_enabled: bool) -> list[str]:
    if not entries:
        return []
    
    max_name_len = max(len(e.name) for e in entries)
    
    if options.long_format:
        # Calculate column widths for alignment
        max_nlink = max(len(str(e.stat_result.st_nlink)) for e in entries)
        max_user = max(len(get_user_group(e, options)[0]) for e in entries)
        max_group = max(len(get_user_group(e, options)[1]) for e in entries if not options.omit_group) if not options.omit_group else 0
        max_size = max(len(format_size(e.stat_result.st_size if not options.size else e.stat_result.st_blocks * 512, options.human_readable)) for e in entries)
        max_time = max(len(format_time(e.stat_result, options)) for e in entries)
        
        lines = []
        for e in entries:
            perms = format_permissions(e.stat_result.st_mode)
            nlink = str(e.stat_result.st_nlink)
            user, group = get_user_group(e, options)
            
            if options.size:
                size = format_size(e.stat_result.st_blocks * 512, options.human_readable)
            else:
                size = format_size(e.stat_result.st_size, options.human_readable)
            
            mtime = format_time(e.stat_result, options)
            
            display_name = quote_name(e.name, options.hide_control_chars)
            suffix = classify_append(e, options)
            name_part = display_name + suffix
            
            nlink_part = nlink.rjust(max_nlink)
            user_part = user.rjust(max_user)
            size_part = size.rjust(max_size)
            time_part = mtime.rjust(max_time)
            
            if options.omit_group:
                line = f"{perms} {nlink_part} {user_part}  {size_part} {time_part} {name_part}"
            else:
                group_part = group.rjust(max_group)
                line = f"{perms} {nlink_part} {user_part} {group_part} {size_part} {time_part} {name_part}"
            lines.append(line)
        return lines
    
    elif options.one_per_line:
        lines = []
        for e in entries:
            display_name = quote_name(e.name, options.hide_control_chars)
            suffix = classify_append(e, options)
            lines.append(display_name + suffix)
        return lines
    
    else:
        col_width = max_name_len + 2
        ncols = max(1, term_width // col_width)
        nrows = (len(entries) + ncols - 1) // ncols
        
        if options.C:
            chunked = [entries[i::ncols] for i in range(ncols)]
        else:
            chunked = [entries[i*ncols:(i+1)*ncols] for i in range(nrows)]
        
        lines = []
        for row in chunked:
            parts = []
            for e in row:
                display_name = quote_name(e.name, options.hide_control_chars)
                suffix = classify_append(e, options)
                parts.append((display_name + suffix).ljust(col_width))
            lines.append(' '.join(parts))
        return lines

def scan_directory(dir_path: str, show_all: bool, almost_all: bool, follow_symlinks: bool, ignore_backups: bool, quote_control: bool) -> List[LsEntry]:
    names = os.listdir(dir_path)
    filtered_names = [n for n in names if show_all or (not n.startswith('.') or (almost_all and n not in {'.', '..'})) and (not ignore_backups or not n.endswith('~'))]
    entries = []
    for name in filtered_names:
        full_path = os.path.join(dir_path, name)
        try:
            entries.append(entry_from_path(full_path, follow_symlinks))
        except OSError:
            pass  # skip unreadable
    return entries

def sort_entries(entries: List[LsEntry], options) -> List[LsEntry]:
    if options.no_sort or options.f:
        return entries  # no sort
    
    time_field = options.time_style.value if hasattr(options, 'time_style') else 'mtime'
    
    base_key = (
        lambda e: getattr(e.stat_result, f'st_{time_field}') if options.t
        else (getattr(e.stat_result, 'st_ctime') if options.c
              else (getattr(e.stat_result, 'st_atime') if options.u
                    else (e.stat_result.st_size if options.S
                          else (os.path.splitext(e.name)[1] + e.name if options.sort_extension
                                else e.name)))))
    
    if options.group_directories_first:
        def dir_key(e):
            return (0 if e.is_dir else 1, base_key(e))
        key = dir_key
    else:
        key = base_key
    
    return sorted(entries, key=key, reverse=options.reverse)

def list_path(path: str, options: argparse.Namespace, term_width: int, color_enabled: bool) -> None:
    abspath = os.path.abspath(path)
    
    try:
        if options.dereference:
            st = os.stat(abspath)
        else:
            st = os.lstat(abspath)
    except OSError:
        print(f"ls: cannot access '{abspath}': No such file or directory", file=sys.stderr)
        return
    
    if options.directory or not stat.S_ISDIR(st.st_mode):
        entry = entry_from_path(abspath, options.dereference)
        lines = format_entries([entry], options, term_width, color_enabled)
        print('\n'.join(lines))
    else:
        print(f"{abspath}:")
        entries = scan_directory(abspath, options.all or options.f, options.almost_all, options.dereference, options.ignore_backups, options.hide_control_chars)
        sorted_entries = sort_entries(entries, options)
        lines = format_entries(sorted_entries, options, term_width, color_enabled)
        print('\n'.join(lines))
        
        if options.recursive:
            subdirs = [e for e in sorted_entries if e.is_dir]
            for subdir_entry in subdirs:
                print()
                list_path(os.path.join(abspath, subdir_entry.name), options, term_width, color_enabled)

def main() -> int:
    try:
        options = parse_arguments(sys.argv[1:])
    except SystemExit:
        return 2

    color_enabled = False
    if options.color == ColorMode.AUTO:
        color_enabled = sys.stdout.isatty()
    elif options.color == ColorMode.ALWAYS:
        color_enabled = True
    elif options.color == ColorMode.NEVER:
        color_enabled = False

    if hasattr(options, 'no_color') and options.no_color:
        color_enabled = False

    try:
        term_size = shutil.get_terminal_size(fallback=(80, 24))
        term_width = term_size.columns
    except:
        term_width = 80

    if options.width is not None:
        term_width = options.width

    error_occurred = False
    for i, path in enumerate(options.paths):
        try:
            if i > 0:
                print()
            list_path(path, options, term_width, color_enabled)
        except Exception:
            error_occurred = True

    return 1 if error_occurred else 0

if __name__ == '__main__':
    sys.exit(main())
