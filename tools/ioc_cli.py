#!/usr/bin/env python3
"""
IOC Monitor — interactive curses TUI for MEOP IOC screen sessions.

    python tools/ioc_cli.py

Keys (main view):
    ↑ / ↓       Select IOC
    s           Start selected IOC
    x           Stop  selected IOC
    r           Restart selected IOC
    l           View log for selected IOC
    a           Attach to screen session (returns on detach)
    S           Start ALL autostart IOCs
    X           Stop  ALL IOCs
    q / Esc     Quit

Keys (log view):
    ↑ / ↓       Scroll
    q / Esc / l Back to main view
"""

import curses
import os
import subprocess
import sys
import time

import yaml
from screenutils import Screen

# ── Paths ──────────────────────────────────────────────────────────────────────
SETTINGS_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'settings.yaml')
)
PROJECT_ROOT = os.path.dirname(SETTINGS_FILE)

REFRESH_SECS = 2          # auto-refresh interval
LOG_TAIL     = 200        # max lines kept in log view


# ── Settings / log helpers ─────────────────────────────────────────────────────
def load_settings():
    with open(SETTINGS_FILE) as f:
        return yaml.safe_load(f)

def ioc_names(settings):
    return [k for k in settings if k != 'general']

def log_path(settings, name):
    log_dir = settings['general']['log_dir']
    if not os.path.isabs(log_dir):
        log_dir = os.path.join(PROJECT_ROOT, log_dir)
    return os.path.normpath(os.path.join(log_dir, name))

def read_log_lines(path, n):
    """Return up to n lines from the end of a log file."""
    if not os.path.exists(path):
        return ['(no log file)']
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            buf, pos = b'', f.tell()
            lines_found = 0
            while pos > 0 and lines_found < n:
                chunk = min(1024, pos)
                pos  -= chunk
                f.seek(pos)
                buf   = f.read(chunk) + buf
                lines_found = buf.count(b'\n')
        lines = buf.decode('utf-8', errors='replace').splitlines()
        return lines[-n:] if lines else ['(empty)']
    except OSError:
        return ['(unreadable)']


# ── Screen / IOC actions ───────────────────────────────────────────────────────
def ioc_running(name):
    return Screen(name).exists

def start_ioc(settings, name):
    if ioc_running(name):
        return f'{name}: already running'
    lp = log_path(settings, name)
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    screen = Screen(name, True)
    screen.send_commands('bash')
    screen.send_commands(f'python master_ioc.py -i {name}')
    screen.enable_logs(lp)
    return f'{name}: started'

def stop_ioc(name):
    if not ioc_running(name):
        return f'{name}: not running'
    subprocess.run(['screen', '-XS', name, 'kill'], check=False)
    return f'{name}: stopped'

def restart_ioc(settings, name):
    stop_ioc(name)
    time.sleep(1)
    return start_ioc(settings, name)


# ── Colour pair indices ────────────────────────────────────────────────────────
C_NORMAL   = 0
C_HEADER   = 1
C_RUNNING  = 2
C_STOPPED  = 3
C_SELECTED = 4
C_STATUS   = 5
C_TITLE    = 6
C_DIM      = 7

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HEADER,   curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(C_RUNNING,  curses.COLOR_GREEN,  -1)
    curses.init_pair(C_STOPPED,  curses.COLOR_RED,    -1)
    curses.init_pair(C_SELECTED, curses.COLOR_BLACK,  curses.COLOR_WHITE)
    curses.init_pair(C_STATUS,   curses.COLOR_BLACK,  curses.COLOR_YELLOW)
    curses.init_pair(C_TITLE,    curses.COLOR_BLACK,  curses.COLOR_BLUE)
    curses.init_pair(C_DIM,      curses.COLOR_YELLOW, -1)


# ── Drawing helpers ────────────────────────────────────────────────────────────
def safe_addstr(win, y, x, text, attr=0):
    """addstr that silently ignores out-of-bounds writes."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    max_len = w - x - 1
    if max_len <= 0:
        return
    try:
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass

def fill_row(win, y, attr):
    h, w = win.getmaxyx()
    if 0 <= y < h:
        try:
            win.addstr(y, 0, ' ' * (w - 1), attr)
        except curses.error:
            pass

def draw_title(win, text):
    fill_row(win, 0, curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(win, 0, 2, text, curses.color_pair(C_TITLE) | curses.A_BOLD)

def draw_status(win, text):
    h, _ = win.getmaxyx()
    fill_row(win, h - 1, curses.color_pair(C_STATUS))
    safe_addstr(win, h - 1, 1, text, curses.color_pair(C_STATUS))

def draw_help(win, keys):
    """Draw a key-hint bar on the second-to-last row."""
    h, w = win.getmaxyx()
    row  = h - 2
    fill_row(win, row, curses.color_pair(C_HEADER))
    x = 1
    for key, desc in keys:
        hint = f' {key}:{desc} '
        if x + len(hint) >= w - 1:
            break
        safe_addstr(win, row, x, hint, curses.color_pair(C_HEADER))
        x += len(hint) + 1


# ── Main list view ─────────────────────────────────────────────────────────────
def draw_main(win, settings, names, selected, status_msg):
    h, w = win.getmaxyx()
    win.erase()

    draw_title(win, ' MEOP IOC Monitor ')

    # Column widths
    col_name = max(len(n) for n in names) + 2
    col_st   = 10
    col_auto = 10
    col_log  = max(w - col_name - col_st - col_auto - 4, 10)

    # Header row
    hdr = (f'{"IOC":<{col_name}}'
           f'{"STATUS":<{col_st}}'
           f'{"AUTO":<{col_auto}}'
           f'{"LAST LOG LINE":<{col_log}}')
    fill_row(win, 1, curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, 1, 1, hdr[:w - 2],
                curses.color_pair(C_HEADER) | curses.A_BOLD)

    # IOC rows (leave 3 rows: title + header + help + status)
    list_rows = h - 4
    # Scroll offset so selected is always visible
    offset = max(0, selected - list_rows + 1)

    for i, name in enumerate(names):
        row = i - offset + 2   # display row
        if row < 2 or row >= h - 2:
            continue

        running   = ioc_running(name)
        autostart = settings[name].get('autostart', False)

        run_label  = 'running' if running  else 'stopped'
        auto_label = 'yes'     if autostart else 'no'

        last_line = read_log_lines(log_path(settings, name), 1)[0].strip()
        if len(last_line) > col_log:
            last_line = last_line[:col_log - 3] + '...'

        line = (f'{name:<{col_name}}'
                f'{run_label:<{col_st}}'
                f'{auto_label:<{col_auto}}'
                f'{last_line:<{col_log}}')

        if i == selected:
            fill_row(win, row, curses.color_pair(C_SELECTED) | curses.A_BOLD)
            safe_addstr(win, row, 1, line[:w - 2],
                        curses.color_pair(C_SELECTED) | curses.A_BOLD)
        else:
            win.move(row, 0)
            run_attr  = (curses.color_pair(C_RUNNING) if running
                         else curses.color_pair(C_STOPPED))
            auto_attr = (curses.color_pair(C_RUNNING) if autostart
                         else curses.color_pair(C_DIM))
            safe_addstr(win, row, 1,          f'{name:<{col_name}}')
            safe_addstr(win, row, 1+col_name, f'{run_label:<{col_st}}',  run_attr)
            safe_addstr(win, row, 1+col_name+col_st,
                        f'{auto_label:<{col_auto}}', auto_attr)
            safe_addstr(win, row, 1+col_name+col_st+col_auto, last_line)

    draw_help(win, [('↑↓','select'),('s','start'),('x','stop'),
                    ('r','restart'),('l','logs'),('a','attach'),
                    ('S','start all'),('X','stop all'),('q','quit')])
    draw_status(win, f'  {status_msg}   (auto-refresh {REFRESH_SECS}s)')
    win.refresh()


# ── Log view ───────────────────────────────────────────────────────────────────
def log_view(stdscr, settings, name):
    """Full-screen scrollable log viewer for one IOC. Returns when user exits."""
    curses.curs_set(0)
    scroll = 0
    status = ''

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        draw_title(stdscr, f' Log: {name} ')

        lines     = read_log_lines(log_path(settings, name), LOG_TAIL)
        view_rows = h - 4          # title + help + status
        max_scroll = max(0, len(lines) - view_rows)
        scroll     = min(scroll, max_scroll)

        for i, line in enumerate(lines[scroll:scroll + view_rows]):
            safe_addstr(stdscr, i + 1, 1, line[:w - 2])

        draw_help(stdscr, [('↑↓','scroll'),('l/q/Esc','back')])
        draw_status(stdscr, f'  {name}  lines {scroll+1}–'
                             f'{min(scroll+view_rows, len(lines))}'
                             f'/{len(lines)}  {status}')
        stdscr.refresh()

        stdscr.timeout(REFRESH_SECS * 1000)
        key = stdscr.getch()

        if key in (ord('q'), ord('l'), 27):   # 27 = Esc
            return
        elif key == curses.KEY_UP:
            scroll = max(0, scroll - 1)
        elif key == curses.KEY_DOWN:
            scroll = min(max_scroll, scroll + 1)
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - (h - 4))
        elif key == curses.KEY_NPAGE:
            scroll = min(max_scroll, scroll + (h - 4))
        # timeout (key == -1): just refresh


# ── Attach helper ──────────────────────────────────────────────────────────────
def do_attach(stdscr, name):
    """Temporarily suspend curses, attach to screen session, resume on return."""
    curses.endwin()
    subprocess.run(['screen', '-r', name])
    # Reinitialise after returning from screen
    stdscr.refresh()
    curses.doupdate()


# ── Main TUI loop ──────────────────────────────────────────────────────────────
def tui(stdscr):
    init_colors()
    curses.curs_set(0)
    settings = load_settings()
    names    = ioc_names(settings)
    selected = 0
    status   = 'Ready'

    while True:
        draw_main(stdscr, settings, names, selected, status)

        stdscr.timeout(REFRESH_SECS * 1000)
        key = stdscr.getch()

        if key == -1:
            # Timeout — just refresh (status already cleared on next draw)
            status = 'Ready'
            continue

        name = names[selected]

        if key in (ord('q'), 27):
            break
        elif key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(len(names) - 1, selected + 1)
        elif key == ord('s'):
            status = start_ioc(settings, name)
        elif key == ord('x'):
            status = stop_ioc(name)
        elif key == ord('r'):
            status = restart_ioc(settings, name)
        elif key == ord('l'):
            log_view(stdscr, settings, name)
            status = f'Returned from log: {name}'
        elif key == ord('a'):
            if ioc_running(name):
                do_attach(stdscr, name)
                status = f'Detached from {name}'
            else:
                status = f'{name} is not running'
        elif key == ord('S'):
            msgs = []
            for n in names:
                if settings[n].get('autostart', False):
                    msgs.append(start_ioc(settings, n))
            status = ' | '.join(msgs) or 'Nothing to start'
        elif key == ord('X'):
            msgs = [stop_ioc(n) for n in names if ioc_running(n)]
            status = ' | '.join(msgs) or 'Nothing running'


def main():
    os.chdir(PROJECT_ROOT)
    try:
        curses.wrapper(tui)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
