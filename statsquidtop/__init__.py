import os
import sys
import signal
import curses
from copy import deepcopy
from datetime import datetime
from redis import StrictRedis
from argparse import ArgumentParser
from curses.textpad import Textbox,rectangle

from statsquidtop.menu import run_menu
from statsquidtop.util import format_bytes, unix_time, convert_type

key_prefix = 'statsquid'

class StatSquidTop(object):
    def __init__(self, redis_host, redis_port, filter=None, sort_key=None):
        self.redis  = StrictRedis(host=redis_host,
                                  port=redis_port,
                                  decode_responses=True)

        #set initial display options
        self.sums = False
        self.filter = filter
        self.sort = { 'key': sort_key, 'reversed': True }

        self.keys   = {
            'name'   : str,
            'source' : str,
            'id'     : str,
            'cpu'    : float,
            'mem'    : float,
            'last_read'            : float,
            'stats_read'           : float,
            'net_rx_bytes_total'   : float,
            'net_tx_bytes_total'   : float,
            'io_read_bytes_total'  : float,
            'io_write_bytes_total' : float
        }
        self.valid_filters = [ k for k,v in list(self.keys.items()) if v == str ]

        self.stats  = {}
        while True:
            self.poll()
            self.display()

    def sig_handler(self, signal, frame):
        curses.endwin()
        sys.exit(0)

    def poll(self):
        last_stats = deepcopy(self.stats)
        self.stats = {}

        #populate self.stats with all containers
        for key in list(self.redis.keys(key_prefix + ':*')):
            container = self._get_container(key)
            if container:
                self.stats[container['id']] = container

        if self.sums:
            self.display_stats = deepcopy(list(self.stats.values()))
        else:
            self.display_stats = self._diff_stats(self.stats,last_stats)

        if self.sort['key']:
            self.display_stats = sorted(self.display_stats,
                    key=self._sorter,reverse=self.sort['reversed'])

        if self.filter:
            ftype,fvalue = self.filter.split(':')
            self.display_stats = [ s for s in self.display_stats \
                                         if fvalue in s[ftype] ]

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
        s.addstr(1, 2, 'statsquid top -')
        s.addstr(1, 18, datetime.now().strftime('%H:%M:%S'))
        s.addstr(1, 28, ('%s containers' % len(self.display_stats)))
        if self.filter:
            s.addstr(1, 42, ('filter: %s' % self.filter))

        #second line
        s.addstr(3, 2, "NAME", curses.A_BOLD)
        s.addstr(3, 25, "ID", curses.A_BOLD)
        s.addstr(3, 41, "CPU", curses.A_BOLD)
        s.addstr(3, 48, "MEM", curses.A_BOLD)
        s.addstr(3, 58, "NET TX", curses.A_BOLD)
        s.addstr(3, 68, "NET RX", curses.A_BOLD)
        s.addstr(3, 78, "READ IO", curses.A_BOLD)
        s.addstr(3, 88, "WRITE IO", curses.A_BOLD)
        s.addstr(3, 98, "SOURCE", curses.A_BOLD)

        #remainder of lines
        line = 5
        maxlines = h - 2
        for stat in self.display_stats:
            s.addstr(line, 2,  stat['name'][:20])
            s.addstr(line, 25, stat['id'][:12])
            s.addstr(line, 41, str(stat['cpu']))
            s.addstr(line, 48, format_bytes(stat['mem']))
            s.addstr(line, 58, format_bytes(stat['net_tx_bytes_total']))
            s.addstr(line, 68, format_bytes(stat['net_rx_bytes_total']))
            s.addstr(line, 78, format_bytes(stat['io_read_bytes_total']))
            s.addstr(line, 88, format_bytes(stat['io_write_bytes_total']))
            s.addstr(line, 98, stat['source'])
            if line >= maxlines:
                break
            line += 1
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

            #format field names for readable output
            opts = list(self.keys.keys())
            fmt_opts = [k.replace('_',' ').replace('total','') for k in opts]

            selected = run_menu(tuple(fmt_opts),x=startx,y=6,name="sort")
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

    def _get_container(self, key):
        """
        Fetch all fields in a hash key from redis, mapping to types defined
        in self.keys. Return None if any keys are missing or last update
        was > 10s ago.
        """
        now = unix_time(datetime.utcnow())
        container = self.redis.hgetall(key)

        if False in [k in container for k in self.keys]:
            return None

        stat = { k:convert_type(container[k],t) for \
                    k,t in list(self.keys.items()) }

        if now - stat['last_read'] > 10:
            return None

        return stat

    def _diff_stats(self,new_stats,last_stats):
        stats = deepcopy(new_stats)
        for cid in stats:
            if cid in last_stats:
                stats[cid] = self._diff_cid(stats[cid],last_stats[cid])
            else:
                stats[cid] = self._zero_stat(stats[cid])
        
        return list(stats.values())

    def _zero_stat(self,stat):
        for k in [ k for k in self.keys if '_total' in k ]:
            stat[k] = 0
        return stat

    def _diff_cid(self,stat,last_stat):
        time_delta = stat['last_read'] - last_stat['last_read']
        diffdict = { k:(last_stat[k],stat[k],time_delta) for \
                        k in self.keys if '_total' in k }
        for k,v in list(diffdict.items()):
            stat[k] = self._get_delta(*v)

        return stat

    def _get_delta(self,old,new,elapsed):
        delta = new - old
        if elapsed > 1 and delta != 0:
            return int(round(delta / elapsed))
        else:
            return delta

def main():
    envvars = { 'STATSQUID_REDIS' : 'redis' }

    parser = ArgumentParser(description='statsquid top v%s' % version)
    parser.add_argument('--redis',
                        dest='redis',
                        help='redis host to connect to (127.0.0.1:6379)',
                        default='127.0.0.1:6379')

    args = parser.parse_args()

    #override command line with env vars
    [ args.__setattr__(v,os.getenv(k)) for k,v in \
            list(envvars.items()) if os.getenv(k) ]

    if ':' in args.redis:
        redis_host,redis_port = args.redis.split(':')
    else:
        redis_host = args.redis
        redis_port = 6379

    StatSquidTop(redis_host, redis_port)

if __name__ == '__main__':
    main()
