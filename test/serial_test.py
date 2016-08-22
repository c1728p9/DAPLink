#
# DAPLink Interface Firmware
# Copyright (c) 2009-2016, ARM Limited, All Rights Reserved
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import absolute_import
from __future__ import division
import Queue
import functools
import serial
import threading
import time

ERROR_TIMEOUT_SECONDS = 10.0


def _same(d1, d2):
    d1 = bytearray(d1)
    d2 = bytearray(d2)

    for i in range(min(len(d1), len(d2))):
        if d1[i] != d2[i]:
            return False
    if len(d1) != len(d2):
        return False
    return True

# http://digital.ni.com/public.nsf/allkb/D37754FFA24F7C3F86256706005B9BE7
standard_baud = [
    9600,
    14400,
    19200,
    28800,
    38400,
    56000,
    57600,
    115200,
    ]
timing_test_baud = standard_baud[3:]


def calc_timeout(length, baud):
    """Calculate a timeout given the data and baudrate

    Positional arguments:
        length - size of data to be sent
        baud - baud rate to send data

    Calculate a reasonable timeout given the supplied parameters.
    This function adds slightly more time then is needed, to accont
    for latency and various configurations.
    """
    return 12 * float(length) / float(baud) + 0.2


class SerialTester(object):
    """Helper object to buffer serial and setup baud"""

    def __init__(self, port):
        self.raw_serial = serial.Serial(port, baudrate=115200)
        self.raw_serial.write_timeout = ERROR_TIMEOUT_SECONDS
        self._queue = Queue.Queue()
        self._write_thread = threading.Thread(target=self._serial_main)
        self._write_thread.start()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, value, traceback):
        self._queue.put(None)
        self._write_thread.join(ERROR_TIMEOUT_SECONDS)
        assert not self._write_thread.isAlive(), "Thread join failed"
        self.raw_serial.close()
        self.raw_serial = None
        return False

    def new_session_with_baud(self, baud, test_info):
        """Start a new session by restarting target and setting baud"""

        # Set baud to 115200
        self.raw_serial.baudrate = 115200
        self.raw_serial.timeout = 1.0

        # Reset the target
        self.raw_serial.sendBreak()

        # Wait until the target is initialized
        expected_resp = "{init}"
        resp = self.read(len(expected_resp))
        if not _same(resp, expected_resp):
            test_info.failure("Fail on init: %s" % resp)
            return False

        # Change baudrate to that of the first test
        command = "{baud:%i}" % baud
        self.write(command)
        resp = self.read(len(command))
        if not _same(resp, command):
            test_info.failure("Fail on baud command: %s" % resp)
            return False

        # Update baud of local serial port
        self.raw_serial.baudrate = baud

        # Read the response indicating that the baudrate
        # on the target has changed
        expected_resp = "{change}"
        resp = self.read(len(expected_resp))
        if not _same(resp, expected_resp):
            test_info.failure("Fail on baud change %s" % resp)
            return False

        # Set default timeout
        self.raw_serial.timeout = ERROR_TIMEOUT_SECONDS

        # Success
        return True

    def read(self, length):
        """Read serial data"""
        return self.raw_serial.read(length)

    def write(self, data):
        """Write serial port data in the background"""
        func = functools.partial(self.raw_serial.write, data[:])
        self._queue.put(func)

    def set_read_timeout(self, timeout):
        """Set timeout for read operations"""
        assert self._queue.empty(), "Queue must be empty to change timeout"
        self.raw_serial.timeout = timeout

    def flush(self):
        """Wait for all writes to complete"""
        self._queue.join()
        assert self._queue.empty()

    def _serial_main(self):
        """Write helper thread"""
        while True:
            task = self._queue.get(True)
            if task is None:
                self._queue.task_done()
                # End of processing is an empty task
                break
            try:
                task()
            except serial.SerialTimeoutException:
                pass
            self._queue.task_done()


def test_serial(workspace, parent_test):
    """Test the serial port endpoint

    Requirements:
        -daplink-validation must be loaded for the target.

    Positional arguments:
        port - the serial port to open as a string

    Return:
        True if the test passed, False otherwise
    """
    test_info = parent_test.create_subtest("Serial test")
    port = workspace.board.get_serial_port()
    test_info.info("Testing serial port %s" % port)

    # Note: OSX sends a break command when a serial port is closed.
    # To avoid problems while testing keep the serial port open the
    # whole time.  Use the property 'baudrate' to change the baud
    # instead of opening a new instance.

    with SerialTester(port) as sp:

#        # Generate a 8 KB block of dummy data
#        # and test a large block transfer
#        test_data = [i for i in range(0, 256)] * 4 * 8
#        test_data = str(bytearray(test_data))
#        sp.new_session_with_baud(115200, test_info)
#
#        sp.write(test_data)
#        resp = sp.read(len(test_data))
#        if _same(resp, test_data):
#            test_info.info("Block test passed")
#        else:
#            test_info.failure("Block test failed")
#
#        # Generate a 4KB block of dummy data
#        # and test supported baud rates
#        test_data = [i for i in range(0, 256)] * 4 * 4
#        test_data = str(bytearray(test_data))
#        for baud in standard_baud:
#
#            test_info.info("Testing baud %i" % baud)
#            success = sp.new_session_with_baud(baud, test_info)
#            if not success:
#                test_info.failure("Unable to setup session")
#                continue
#
#            # Perform test
#            sp.write(test_data)
#            resp = sp.read(len(test_data))
#            resp = bytearray(resp)
#            if _same(test_data, resp):
#                test_info.info("Pass")
#            else:
#                test_info.failure("Fail on baud %s" % baud)
#
#        # Timing stress test - send data at critical points
#        # in time like right as the transmitter is turned off
#        # ------------------
#        # Test sequence
#        # 1. Send a block of data (vary size for the test)
#        # 2. Wait until 1 byte is read back
#        # 3. Write 1 byte
#        # 4. Read back all data
#        test_data = [i for i in range(0, 256)] * 4 * 4
#        test_data = str(bytearray(test_data))
#        for baud in timing_test_baud:
#
#            test_info.info("Timing test baud %i" % baud)
#            success = sp.new_session_with_baud(baud, test_info)
#            if not success:
#                test_info.failure("Unable to setup session")
#                continue
#
#            test_pass = True
#            for data_size in range(1, 10):
#                data = test_data[0:data_size + 1]
#                for _ in range(0, 1000):
#                    resp = bytearray()
#
#                    sp.write(data[0:data_size])
#                    resp += sp.read(1)
#                    sp.write(data[-1:])
#                    resp += sp.read(data_size)
#                    sp.flush()
#                    if not _same(data, resp):
#                        test_pass = False
#                        test_info.info("fail size - %s" % data_size)
#                        break
#
#            if test_pass:
#                test_info.info("Pass")
#            else:
#                test_info.failure("Fail on timing test with baud %s"
#                                  % baud)


    # Buffers that must be cleared on a new session
    # 1. PC buffer
    # 2. DAPLink USB buffer
    # 3. DAPLink UART buffer
    #    - On on setting change (baud rate)
    #    - On serial break

    # Test settings change?


    # Serial break
    # -first thing after it should be "init" regardless of prev stuff
    #    -open a new session to clear buffer
    #    -send break to reset device buffer

    # First thing after a new session


    # Guarentees
    # 1. DAPLink buffers must be cleared on a reset
    # 2. DAPLink buffers must be cleared on a setting change

#    for _ in range(5):
#        with SerialTester(port) as sp:
#            sp.new_session_with_baud(9600, test_info)
#
#    with serial.Serial(port, baudrate=115200) as sp:
#        sp.timeout = 0.5
#
#        sp

        # Buffer test - Test buffering to make sure it gets cleared
        # at the appropriate times.

#        #TODO - verify on atsam3u
#        test_data = [i for i in range(0, 256)] * 4
#        test_data = str(bytearray(test_data))
#        for i in range(5):
#            sp.new_session_with_baud(9600, test_info)
#
#            sp.raw_serial.write(test_data)
#            sp.raw_serial.flush()
#
#            # Change baud rate - this should clear daplink's buffers
#            sp.raw_serial.baudrate = 115200
#            sp.raw_serial.baudrate = 9600
#
#            # Flush PC RX buffer
#            sp.raw_serial.flushInput()
#
#            # Fail if more data is read
#            sp.raw_serial.timeout = 0.1
#            data = sp.raw_serial.read(1)
#            if len(data) != 0:
#                test_info.failure("Failed to clear buffer on setting change")
#                break

        test_data = [i for i in range(0, 256)] * 4 * 16
        test_data = str(bytearray(test_data))
        for i in range(10):
            sp.new_session_with_baud(115200, test_info)
            sp.raw_serial.timeout = 0.5

            write_start = time.time()
            sp.raw_serial.write(test_data)
            sp.raw_serial.flushOutput()
            sp.raw_serial.flush()
            write_end = time.time()
            print("Elapsed write time: %s" % (write_end - write_start))

            #sp.raw_serial.flushInput()

            # Send break - this should clear daplink's buffers

            #sp.raw_serial.read(len(test_data))
            sp.raw_serial.sendBreak()

            #sp.raw_serial.baudrate = 9600
            #sp.raw_serial.baudrate = 115200
            #sp.raw_serial.timeout = 0.5
            #sp.raw_serial.flush()

            #time.sleep(5)
            # Flush PC RX buffer
            #print("waiting: %s" % sp.raw_serial.in_waiting)
            #sp.raw_serial.timeout = 0
            #data = sp.raw_serial.read(16 * 1024)
            #print("Size read after waiting: %s" % len(data))
            #data = sp.raw_serial.read(16 * 1024)
            #print("Size read after waiting2: %s" % len(data))
            #sp.raw_serial.flushInput()
            #sp.raw_serial.flushOutput()

            expected_resp = "{init}"
            resp = sp.raw_serial.read(16 * 1024)
            if not _same(resp, expected_resp):
                test_info.failure("Buffer clear on break failed: %s" % len(resp))
                break

        # Verify data is flushed between sessions
        #-pc TX buffer
        #-pc RX buffer

