# -*- coding:utf-8 -*-
"""Login H3C switch device, and execute some commands.

H3C server implement a non-standard SSH2 server, we can't use `paramiko.client.SSHClient()` directly
to log on to the server to execute command, it will raise an error like
`paramiko.SSHException: Channel closed`. You have to connect the server via starting a channel on
an interact shell.
"""

from collections import defaultdict
import socket
import logging
import paramiko

__author__ = "lqs"


class SSH2:
    def __init__(self, username=None, password=None, host=None, port=22, buffersize=1024):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.buffersize = buffersize
        self.logger = logging.getLogger(__file__)
        self.ssh = None
        self.chan = None

    def __del__(self):
        if self.chan is not None:
            self.chan.close()
            self.chan = None

        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None

    def make_chan(self):
        self.logger.debug('Connecting {0}@{1}:{2}'.format(self.username, self.host, self.port))

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.ssh.connect(hostname=self.host, port=self.port, username=self.username,
                             password=self.password)
            self.chan = self.ssh.invoke_shell(width=120, height=200)
        except socket.error:
            self.chan = None
            self.logger.error('Socket error on connecting {0}@{1}:{2}'.format(self.username,
                                                                              self.host, self.port))
        except paramiko.AuthenticationException:
            self.chan = None
            self.logger.error('Invalid username or password.')
        except paramiko.SSHException:
            self.chan = None
            self.logger.error('Establishing or connecting SSH session failed.')

        return self.chan is not None

    @property
    def connected(self):
        return self.chan is not None

    def _execute(self, command, timeout=6):
        results = b''
        self.chan.settimeout(timeout)

        try:
            while True:
                # May hang here, so we must set ``channel`` object a timeout.
                # Note: if we set the timeout, the data received may not be complete.
                data = self.chan.recv(self.buffersize)

                # Skip the warning or welcome messages.
                if data.startswith(b'\r\r\n') or data.startswith(b'*'):
                    continue

                # Execute the command.
                # Note: The command may be executed twice, refer to:
                # https://erlerobotics.gitbooks.io/erle-robotics-python-gitbook-free/content/telnet_and_ssh/shell_sessions_and_individual_commands.html
                # It is strange that it happens occasionally, not always.
                if data.startswith(b'<SH-'):
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
        self.logger.info('Initialize a session to execute the command.')

        if not self.connected:
            self.make_chan()

        outputs = self._execute(command)
        return outputs

    def _parse(self, data):
        ret = []

        # The command may not be executed completely, or may be executed twice.
        nums = [num for num, line in enumerate(data) if line.startswith('<SH-')]
        if len(nums) < 2:
            raise OSError('The output of the command is not complete.')
        if len(nums) > 2:
            data = data[:sorted(nums)[1]]

        for line in data:
            if line == '---- More ----' or line.startswith('<SH-'):
                continue
            ret.extend([x.strip() for x in line.split(' Y') if x.strip()])

        item = ret.pop(0)
        ret.insert(0, item.split('Aging')[1])
        return ret

    def parse_output(self, output):
        results = defaultdict(list)

        ret = self._parse([x.strip().decode() for x in output.splitlines() if x.strip()])
        for item in ret:
            x = item.split()
            if len(x) <= 3:
                print('Invalid data: ', x)
                continue

            if int(x[3].split('BAGG')[1]) <= 48:
                results[x[3]].append(x[0])

        return results

def main():
    command = 'dis mac-address'
    with open('ips') as f:
        for line in f.readlines():
            auth = [i.strip() for i in line.split()]
            ssh = SSH2(host=auth[0], username=auth[1], password=auth[2])
            output = ssh.execute(command)
            data = ssh.parse_output(output)

            for key in sorted(data, key=lambda x: int(x.split('BAGG')[1].strip())):
                print((key, data[key]))
            #
            # with open('result_{}'.format(auth[0]), 'wb') as f:
            #     f.write(data)

if __name__ == '__main__':
    main()
