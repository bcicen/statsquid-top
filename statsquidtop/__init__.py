import os
import sys
import ssl
import json
import signal
import curses
import websocket
from time import sleep
from copy import deepcopy
from datetime import datetime
from threading import Thread
from argparse import ArgumentParser
from curses.textpad import Textbox,rectangle

from menu import run_menu
from util import format_bytes
from columns import columns, hidden_columns

version = '0.1'
_startcol = 2

class StatSquidClient(object):
    def __init__(self, url):
        self.eventQ = []

        self._url = url
        self._thread = Thread(target=self._open)
        self._thread.daemon = True
        self._thread.start()

    def _open(self):
        self._send_id = 0
        self.ws = websocket.WebSocketApp(self._url,
                                         on_message=self._event_handler,
                                         on_error=self._error_handler,
                                         on_open=self._open_handler,
                                         on_close=self._exit_handler)
        self.ws.run_forever(sslopt={'cert_reqs': ssl.CERT_NONE})

    def _event_handler(self, ws, event_bytes):
        event_str = event_bytes.decode('UTF-8')
        self.eventQ.append(json.loads(event_str))

    def _open_handler(self, ws):
        self.connected = True

    def _error_handler(self, ws, error):
        log.critical('websocket error:\n %s' % error)

    def _exit_handler(self, ws):
        log.warn('websocket connection closed')

class StatSquidTop(object):
    def __init__(self, mantle_host, filter=None):
        self.client = StatSquidClient('ws://%s/ws' % mantle_host)

        self.containers = {}
        self.selected_container = None
        self.container_zoom = False

        self.cursor_pos = 0
        self.scroll_pos = 0

        self.sums = False
        self.filter = filter
        self.sort = { 'func': lambda x: x['Names'][0].strip('/'), 'reversed': False }

        signal.signal(signal.SIGINT, self.sig_handler)

        while True:
            self.read_from_queue()
            if self.container_zoom:
                self.display_container()
            else:
                self.display()

    def sig_handler(self, signal, frame):
        curses.endwin()
        sys.exit(0)

    def read_from_queue(self):
        while True:
            try:
                event = self.client.eventQ.pop(0)
            except IndexError:
                break
            self.containers[event['ID']] = event

    def display(self):
        s = curses.initscr()
        curses.noecho()
        curses.curs_set(0)
        s.border(0)
        s.keypad(1)
        s.timeout(1000)

        h,w = s.getmaxyx()
        s.clear()
       
        #first line
        s.addstr(1, 2, 'statsquid-top -')
        s.addstr(1, 18, datetime.now().strftime('%H:%M:%S'))
        s.addstr(1, 28, ('%s containers' % len(self.containers)))
        if self.filter:
            s.addstr(1, 42, ('filter: %s' % self.filter))

        #second line, column headers
        x_pos = _startcol
        for c in columns:
            s.addstr(3, x_pos, c['header'], curses.A_BOLD)
            x_pos += c['width']

        #remainder of lines
        y_pos = 5
        maxlines = h - 2

        for i, container in enumerate(self._format_containers()):
            x_pos = _startcol
            for c in columns:
                value = str(c['value_func'](container))
                if c['is_bytes']:
                    value = format_bytes(value)
                if len(value) >= c['width']:
                    value = self._truncate(value, c['width'])
                if i == self.cursor_pos:
                    style = curses.A_REVERSE+curses.A_BOLD
                    self.selected_container = container['ID']
                else:
                    style = curses.A_NORMAL
                s.addstr(y_pos, x_pos, value, style)
                x_pos += c['width']
            if y_pos >= maxlines:
                break
            else:
                y_pos += 1

        s.refresh()

        x = s.getch()
        if x == ord('q'):
            curses.endwin()
            sys.exit(0)

        if x == ord('h') or x == ord('?'):
            s.clear()
            startx = int(w / 2 - 25) # I have no idea why this offset of 20 is needed

            s.addstr(6, startx+1, 'statsquid top version %s' % version)
            s.addstr(8, startx+1, 'c - toggle between cumulative and current view')
            s.addstr(9, startx+1, 's - select sort field')
            s.addstr(9, startx+1, 'r - reverse sort order')
            s.addstr(10, startx+1, 'f - filter by container name')
            s.addstr(11, startx+5, '(e.g. source:localhost)')
            s.addstr(12, startx+1, 'h - show this help dialog')
            s.addstr(13, startx+1, 'q - quit')

            rectangle(s, 7,startx, 14,(startx+48))
            s.refresh()
            s.nodelay(0)
            s.getch()
            s.nodelay(1)
            
        if x == ord('c'):
            self.sums = not self.sums

        if x == ord('r'):
            self.sort['reversed'] = not self.sort['reversed']

        if x == ord('s'):
            startx = int(w / 2 - 20)

            opts = [ c['header'] for c in columns ]
            selected = run_menu(tuple(opts), x=startx, y=6, name="sort")
            self.sort['func'] = columns[selected]['value_func']

        if x == ord('f'):
            startx = int(w / 2 - 20)

            s.addstr(6, startx, 'String to filter for:')

            editwin = curses.newwin(1,30, 12,(startx+1))
            rectangle(s, 11,startx, 13,(startx+31))
            curses.curs_set(1) #make cursor visible in this box
            s.refresh()

            box = Textbox(editwin)
            box.edit()

            self.filter = str(box.gather()).strip(' ')
            curses.curs_set(0)
            
            #check if valid filter
            if not self._validate_filter():
                self.filter = None
                s.clear()
                s.addstr(6, startx+5, 'Invalid filter')
                s.refresh()
                curses.napms(800)

        ####
        # Cursor scrolling / selection
        ####

        maxcursor = maxlines - 6

        if x == curses.KEY_DOWN:
            if self.scroll_pos < len(self.containers) - maxcursor:
                if self.cursor_pos >= maxcursor:
                    self.scroll_pos += 1
            if self.cursor_pos < len(self.containers):
                self.cursor_pos += 1

        if x == curses.KEY_UP:
            if self.cursor_pos <= maxcursor and self.scroll_pos > 1:
                self.scroll_pos -= 1
            if self.cursor_pos >= 1:
                self.cursor_pos -= 1


        if x == ord('\n') or x == 32 :
            self.container_zoom = True

    def display_container(self):
        s = curses.initscr()
        curses.noecho()
        curses.curs_set(0)
        s.border(0)
        s.keypad(1)
        s.timeout(1000)
        h,w = s.getmaxyx()
        s.clear()

        y_pos = 7
        startx = int(w / 2 - 25)

        container = self.containers[self.selected_container]

        all_cols = columns + hidden_columns
        for c in all_cols:
            value = str(c['value_func'](container))
            if c['is_bytes']:
                value = format_bytes(value)
            spacer = (20 - len(c['header'])) * ' '
            s.addstr(y_pos, startx+3, '%s:%s%s' % (c['header'], spacer, value))
            y_pos += 1

        rectangle(s, 5, startx, 8 + len(all_cols), (startx+48))
        s.refresh()
        x = s.getch()
        if x != -1 :
            self.container_zoom = False

    def _format_containers(self):
        s = sorted(self.containers.values(),
                   key=self.sort['func'],
                   reverse=self.sort['reversed'])
        return s[self.scroll_pos:]

    def _truncate(self, s, max_len):
        i = max_len - 4
        return s[:i] + '...'

    def _validate_filter(self):
        if not self.filter:
            return True

        if ':' not in self.filter:
            return False

        ftype,fvalue = self.filter.split(':')
        if ftype not in self.valid_filters:
            return False

        return True

def main():
    parser = ArgumentParser(description='statsquid-top v%s' % version)
    parser.add_argument('--mantle',
                        dest='mantle',
                        help='mantle host to connect to (127.0.0.1:1234)',
                        default='127.0.0.1:1234')

    args = parser.parse_args()
    StatSquidTop(args.mantle)

if __name__ == '__main__':
    main()
