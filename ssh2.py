# -*- coding:utf-8 -*-
"""Login H3C switch device, and execute some commands.

H3C server implement a non-standard SSH2 server, we can't use `paramiko.client.SSHClient()` directly
to log on to the server to execute command, it will raise an error like
`paramiko.SSHException: Channel closed`. You have to connect the server via starting a channel on
an interact shell.
"""

from collections import defaultdict
from itertools import groupby
import socket
import re
import os.path
import logging
import paramiko

__author__ = "lqs"

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)


class SSH2:
    def __init__(self, username=None, password=None, host=None, port=22, buffersize=1024):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.buffersize = buffersize
        self.ssh = None
        self.chan = None

        self.make_chan()

    def __del__(self):
        if self.chan is not None:
            self.chan.close()
            self.chan = None

        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None

    def make_chan(self):
        logger.info('Connecting [{0}@{1}:{2}]'.format(self.username, self.host, self.port))

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.ssh.connect(hostname=self.host, port=self.port, username=self.username,
                             password=self.password)
            self.chan = self.ssh.invoke_shell(width=120, height=200)
        except socket.error:
            self.chan = None
            logger.error('Socket error on connecting [{0}@{1}:{2}]'.format(self.username,
                                                                           self.host, self.port))
        except paramiko.AuthenticationException:
            self.chan = None
            logger.error('Invalid username or password.')
        except paramiko.SSHException:
            self.chan = None
            logger.error('Establishing or connecting SSH session failed.')

    def shutdown(self):
        self.__del__()

    def _execute(self, command, timeout=30):
        results = b''
        self.chan.settimeout(timeout)

        try:
            while True:
                # May hang here, so we must set ``channel`` object a timeout.
                # Note: if we set the timeout, the data received may not be complete.
                data = self.chan.recv(self.buffersize)

                # Execute the command.
                # Note: The command may be executed twice, refer to:
                # https://erlerobotics.gitbooks.io/erle-robotics-python-gitbook-free/content/telnet_and_ssh/shell_sessions_and_individual_commands.html
                # It is strange that it happens occasionally, not always.
                if re.match(b'<\w.*>', data):
                    self.chan.send(command+'\n')
                    if self.chan.recv_ready():
                        data = self.chan.recv(self.buffersize)

                if b' More ' in data:
                    self.chan.send('\n')
                    if self.chan.recv_ready():
                        data = self.chan.recv(self.buffersize)

                if len(data) == 0:
                    break

                results += data
        except socket.timeout:
            pass

        return results

    def execute(self, command):
        if not self.chan:
            logger.info('Channel is not open. Starting to make a channel.')
            self.make_chan()

        logger.info('Starting to execute [{}].'.format(command))
        outputs = self._execute(command)
        return outputs

# Learn from the python3-cookbook.
def dedupe(items, key=None):
    seen = set()
    for item in items:
        val = item if key is None else key(item)
        if val not in seen:
            seen.add(item)
    return list(seen)

def get_mac_addr(data):
    """Extract from the original bytes string received from channel to get valid mac addresses.

    Note: Because the ``timeout``, the data may be incomplete; or because the command may be
    executed twice, the data may contain duplicate items.
    """
    outputs = defaultdict(list)
    ret = []

    # Find the first literal hostname looks like ``<AA-BB-C01>``, and skip the warning or welcome
    # message.
    host = re.search(b'<\w.*>', data)
    if not host:
        raise IOError('Command has not been executed.')

    pre_ret = data.split(host.group())
    if not pre_ret:
        raise IOError('No outputs')

    if len(pre_ret) < 3:
        logger.warning('Outputs may be incomplete.')

    lines = [line.strip() for line in pre_ret[1].splitlines() if line.strip()]
    for line in lines:
        # skip the useless line or useless line.
        # Note: Some valid line may also be splited into more than one parts.
        try:
            mac, vlan, state, port, age = line.split()
        except ValueError:
            logger.error('Invalid format of line: {}'.format(line.decode()))
            continue
        outputs[port.strip().decode()].append(mac.strip().decode())

    # Erase the useless items and expand mac-addresses.
    for k in outputs:
        if len(outputs[k]) > 5:
            continue
        for mac in outputs[k]:
            ret.append(' '.join([k, mac]))

    return ret

