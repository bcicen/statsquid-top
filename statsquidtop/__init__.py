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

#from statsquidtop.menu import run_menu
from util import format_bytes

version = '0.1'
_startcol = 2

columns = [
        {
            'header': 'NAME',
            'width': 20,
            'value_func': lambda x: x['Names'][0].strip('/'),
            'sort_func': None
        },
        {
            'header': 'CPU %',
            'width': 8,
            'value_func': lambda x: round(x['CPUPercentage'], 2),
            'sort_func': None
        },
        {
            'header': 'MEM',
            'width': 10,
            'value_func': lambda x: format_bytes(x['memory_stats']['usage']),
            'sort_func': None
        },
        {
            'header': 'NET TX',
            'width': 10,
            'value_func': lambda x: format_bytes(x['TxBytesTotal']),
            'sort_func': None
        },
        {
            'header': 'NET RX',
            'width': 10,
            'value_func': lambda x: format_bytes(x['RxBytesTotal']),
            'sort_func': None
        },
        {
            'header': 'IO READ',
            'width': 10,
            'value_func': lambda x: format_bytes(x['IoReadBytesTotal']),
            'sort_func': None
        },
        {
            'header': 'IO WRITE',
            'width': 10,
            'value_func': lambda x: format_bytes(x['IoWriteBytesTotal']),
            'sort_func': None
        },
        {
            'header': 'NODE',
            'width': 11,
            'value_func': lambda x: x['NodeName'],
            'sort_func': None
        }
    ]

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
    def __init__(self, mantle_host, filter=None, sort_key=None):
        self.client = StatSquidClient('ws://%s/ws' % mantle_host)
        self.containers = {}

        #set initial display options
        self.sums = False
        self.filter = filter
        self.sort = { 'key': sort_key, 'reversed': True }

        self.stats  = {}
        while True:
            self.read_from_queue()
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

#        last_stats = deepcopy(self.stats)
#        self.stats = {}
#
#        #read all in incoming_stats queue
#        while True:
#            try:
#                stat = incoming_stats.pop(0)
#                self.stats[stat['ID']] = stat
#            except IndexError:
#                break
#
#        if self.sums:
#            self.display_stats = deepcopy(list(self.stats.values()))
#        else:
#            self.display_stats = self._diff_stats(self.stats,last_stats)
#
#        if self.sort['key']:
#            self.display_stats = sorted(self.display_stats,
#                    key=self._sorter,reverse=self.sort['reversed'])
#
#        if self.filter:
#            ftype,fvalue = self.filter.split(':')
#            self.display_stats = [ s for s in self.display_stats \
#                                         if fvalue in s[ftype] ]

    def display(self):
        s = curses.initscr()
        curses.noecho()
        curses.curs_set(0)
        s.timeout(1000)
        s.border(0)

        h,w = s.getmaxyx()
        signal.signal(signal.SIGINT, self.sig_handler)
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

        for _, container in self.containers.items():
            x_pos = _startcol
            for c in columns:
                value = str(c['value_func'](container))
                if len(value) >= c['width']:
                    value = self._truncate(value, c['width'])
                s.addstr(y_pos, x_pos, value)
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
            startx = w / 2 - 20 # I have no idea why this offset of 20 is needed

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
            startx = w / 2 - 20 # I have no idea why this offset of 20 is needed

            opts = [ c['header'] for c in columns ]
            selected = run_menu(tuple(opts), x=startx, y=6, name="sort")
            self.sort['key'] = opts[selected]

        if x == ord('f'):
            startx = w / 2 - 20 # I have no idea why this offset of 20 is needed

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

    def _truncate(self, s, max_len):
        i = max_len - 4
        return s[:i] + '...'

    def _sorter(self,d):
        return d[self.sort['key']]

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
