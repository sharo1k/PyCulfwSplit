# Copyright 2021 Ezra Morris
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
from contextlib import ExitStack
from telnetlib import Telnet
import os
import pty
from selectors import DefaultSelector as Selector, EVENT_READ
import sys
import tty


def run(num_ports, telnetaddr, port, debug=False):
    """Creates several serial ports. When data is received from one port, sends
    to respective culfw slot."""
    #Has to be done line by line, as commands might mix up
    if debug:
        print('Connecting to',telnetaddr,'on',port)
    try:
        t_obj = Telnet(telnetaddr,port)
    except Exception as e:
        print('Error opening telnet:')
        print(e)
        return
    master_files = {}  # Dict of master fd to master file object.
    slave_names = {}  # Dict of master fd to slave name.
    master_num = {} # Dict of master index to fd
    slave_num = {} # Dict of slaves fd to index
    print('0 port as telnet');
    for idx in range(num_ports):
        master_fd, slave_fd = pty.openpty()
        tty.setraw(master_fd)
        os.set_blocking(master_fd, False)
        slave_name = os.ttyname(slave_fd)
        master_files[master_fd] = open(master_fd, 'r+b',buffering=0)
        master_num[idx+1] = master_fd
        slave_names[master_fd] = slave_name
        print(idx+1, 'port as', slave_name)
        slave_num[master_fd]=idx

    master_files[t_obj.fileno()]=t_obj
    slave_names[t_obj.fileno()]='telnet'
    master_num[0]= t_obj.fileno()

    with Selector() as selector, ExitStack() as stack:
        # Context manage all the master file objects, and add to selector.
        for fd, f in master_files.items():
            stack.enter_context(f)
            selector.register(fd, EVENT_READ)
        try:
            while True:
                for key, events in selector.select():
                    if not events & EVENT_READ:
                        continue
                    if slave_names[key.fileobj] == 'telnet':
                        data = master_files[key.fileobj].read_until(b'\r\n',2)
                        #write to slot
                        cnt= data.count(b'*',0,5)
                        print ('count',cnt, 'fd',slave_names[master_num[cnt+1]])
                        master_files[master_num[cnt+1]].write(data.lstrip(b'*'*cnt))
                    else:
                        newline = False
                        data=b''
                        while not newline:
                           try:
                               data += master_files[key.fileobj].read()
                           except:
                               pass
                           if data.count(b'\n')>0: newline = True
                        #write to telnet
                        data= data.rjust(len(data)+slave_num[key.fileobj],b'*')
                        master_files[master_num[0]].write(data)
                    if debug:
                        print(slave_names[key.fileobj], data, file=sys.stderr)

#        except (KeyboardInterrupt, BaseException):
        except Exception as e:
            print(e)
            # Closing all FDs
            for fd, f in master_files.items():
                f.close()

def main():
    parser = argparse.ArgumentParser(
        description='Create a hub of virtual serial ports, which will stay '
        'available until the program exits. Once set up, the port names be '
        'printed to stdout, one per line.'
    )
    parser.add_argument('-s','--serials', type=int, default=4,
                        help='number of ports to stack')
    parser.add_argument('telnetaddr',type=str,
                        help='address of CUN')
    parser.add_argument('-p','--port', type=int, default=2323,
			help='port of CUN')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='log received data to stderr')
    args = parser.parse_args()

    # Catch KeyboardInterrupt so it doesn't print traceback.
    try:
        run(args.serials, args.telnetaddr, args.port, args.debug)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
