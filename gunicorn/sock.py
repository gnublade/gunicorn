
import errno
import logging
import os
import socket
import sys
import time

log = logging.getLogger(__name__)

class BaseSocket(object):
    
    def __init__(self, addr, fd=None):
        self.address = addr
        if fd is None:
            sock = socket.socket(self.FAMILY, socket.SOCK_STREAM)
        else:
            print "%r" % fd
            sock = socket.fromfd(fd, self.FAMILY, socket.SOCK_STREAM)
        self.sock = self.set_options(sock, bound=(fd is not None))
    
    def __str__(self, name):
        return "<socket %d>" % self.sock.fileno()
    
    def __getattr__(self, name):
        return getattr(self.sock, name)
    
    def set_options(self, sock, bound=False):
        if not bound:
            sock.bind(self.address)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(0)
        sock.listen(2048)
        return sock

class TCPSocket(BaseSocket):
    
    FAMILY = socket.AF_INET
    
    def __str__(self):
        return "http://%s:%d" % self.address
    
    def set_options(self, sock, bound=False):
        if hasattr(socket, "TCP_CORK"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 1)
        elif hasattr(socket, "TCP_NOPUSH"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NOPUSH, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return super(TCPSocket, self).set_options(sock, bound=bound)

class UnixSocket(BaseSocket):
    
    FAMILY = socket.AF_UNIX
    
    def __init__(self, addr, fd=None):
        if fd is None:
            try:
                os.remove(addr)
            except OSError:
                pass
        super(UnixSocket, self).__init__(addr, fd=fd)
    
    def __str__(self):
        return "unix://%s" % self.address

def create_socket(addr):
    """\
    Create a new socket for the given address. If the
    address is a tuple, a TCP socket is created. If it
    is a string, a Unix socket is created. Otherwise
    a TypeError is raised.
    """
    if isinstance(addr, tuple):
        sock_type = TCPSocket
    elif isinstance(addr, basestring):
        sock_type = UnixSocket
    else:
        raise TypeError("Unable to create socket from: %r" % addr)

    if 'GUNICORN_FD' in os.environ:
        fd = int(os.environ.pop('GUNICORN_FD'))
        try:
            return sock_type(addr, fd=fd)
        except socket.error, e:
            if e[0] == errno.ENOTCONN:
                log.error("GUNICORN_FD should refer to an open socket.")
            else:
                raise

    # If we fail to create a socket from GUNICORN_FD
    # we fall through and try and open the socket
    # normally.
    
    for i in range(5):
        try:
            return sock_type(addr)
        except socket.error, e:
            if e[0] == errno.EADDRINUSE:
                log.error("Connection in use: %s" % str(addr))
            if e[0] == errno.EADDRNOTAVAIL:
                log.error("Invalid address: %s" % str(addr))
                sys.exit(1)
            if i < 5:
                log.error("Retrying in 1 second.")
                time.sleep(1)
          
    log.error("Can't connect to %s" % str(addr))
    sys.exit(1)