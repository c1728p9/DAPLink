#
# DAPLink Interface Firmware
# Copyright (c) 2016-2016, ARM Limited, All Rights Reserved
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

import usb.util


class USBCdc(object):

    # Communication commands documented in
    # PSTN120 inside CDC1.2_WMC1.1_012011

    CLASS_CDC_DATA = 0xa
    CLASS_CDC_COMM = 0x2

    FORMAT_STOP_BITS_1_0 = 0
    FORMAT_STOP_BITS_1_5 = 1
    FORMAT_STOP_BITS_2_0 = 2

    PARITY_NONE = 0
    PARITY_ODD = 1
    PARITY_EVEN = 2
    PARITY_MARK = 3
    PARITY_SPACE = 4

    DATA_BITS_5 = 5
    DATA_BITS_6 = 6
    DATA_BITS_7 = 7
    DATA_BITS_8 = 8
    DATA_BITS_16 = 16

    SEND_BREAK_ON = 0xFFFF
    SEND_BREAK_OFF = 0x0000

    def __init__(self, device):
        self._dev = device
        self._if_data = None
        self._if_comm = None
        self.ep_data_out = None
        self.ep_data_in = None
        self._locked = False

        # Find interfaces
        for interface in device.get_active_configuration():
            if interface.bInterfaceClass == USBCdc.CLASS_CDC_DATA:
                assert self._if_data is None
                self._if_data = interface
            if interface.bInterfaceClass == USBCdc.CLASS_CDC_COMM:
                assert self._if_comm is None
                self._if_comm = interface
        assert self._if_data is not None
        assert self._if_comm is not None

        # Find endpoints
        for endpoint in self._if_data:
            if endpoint.bEndpointAddress & 0x80:
                assert self.ep_data_in is None
                self.ep_data_in = endpoint
            else:
                assert self.ep_data_out is None
                self.ep_data_out = endpoint
        assert self.ep_data_in is not None
        assert self.ep_data_out is not None

    def lock(self):
        """Acquire exclisive access to CDC"""
        assert not self._locked

        for interface in (self._if_data, self._if_comm):
            num = interface.bInterfaceNumber
            try:
                if self._dev.is_kernel_driver_active(num):
                    self._dev.detach_kernel_driver(num)
            except NotImplementedError:
                pass
            except usb.core.USBError:
                pass
            usb.util.claim_interface(self._dev, num)
        self._locked = True

    def unlock(self):
        """Release exclusive access to CDC"""
        assert self._locked

        for interface in (self._if_data, self._if_comm):
            num = interface.bInterfaceNumber
            usb.util.release_interface(self._dev, num)
            try:
                self._dev.attach_kernel_driver(num)
            except NotImplementedError:
                pass
            except usb.core.USBError:
                pass
        self._locked = False

    def set_line_coding(self, baud, fmt=FORMAT_STOP_BITS_1_0,
                        parity=PARITY_NONE, databits=DATA_BITS_8):
        """Send the SetLineCoding CDC command"""
        assert self._locked

        data = bytearray(7)
        data[0] = (baud >> (8 * 0)) & 0xFF
        data[1] = (baud >> (8 * 1)) & 0xFF
        data[2] = (baud >> (8 * 2)) & 0xFF
        data[3] = (baud >> (8 * 3)) & 0xFF
        data[4] = fmt
        data[5] = parity
        data[6] = databits

        bmRequestType = 0x21
        bmRequest = 0x20                            # SET_LINE_CODING
        wValue = 0                                  # Always 0 for this request
        wIndex = self._if_comm.bInterfaceNumber     # Communication interface
        self._dev.ctrl_transfer(bmRequestType, bmRequest, wValue, wIndex, data, 1000000)

    def get_line_coding(self):
        """Send the GetLineCoding CDC command

        Returns a tuple containing
        baud, fmt, parity, databits
        """
        assert self._locked

        bmRequestType = 0xA1
        bmRequest = 0x21                            # GET_LINE_CODING
        wValue = 0                                  # Always 0 for this request
        wIndex = self._if_comm.bInterfaceNumber     # Communication interface
        resp = self._dev.ctrl_transfer(bmRequestType, bmRequest, wValue,
                                       wIndex, 7, 100000)
        baud = (((resp[0] & 0xFF) << (8 * 0)) |
                ((resp[1] & 0xFF) << (8 * 1)) |
                ((resp[2] & 0xFF) << (8 * 2)) |
                ((resp[3] & 0xFF) << (8 * 3)))
        fmt = resp[4]
        parity = resp[5]
        databits = resp[6]
        return (baud, fmt, parity, databits)

    def send_break(self, break_time):
        """Send the SendBreak CDC command"""
        assert self._locked
        assert break_time & ~0xFFFF == 0, "Value outside of supported range"

        bmRequestType = 0x21
        bmRequest = 0x23                            # SEND_BREAK
        wValue = break_time                         # Duration of break in ms
        wIndex = self._if_comm.bInterfaceNumber     # Communication interface
        self._dev.ctrl_transfer(bmRequestType, bmRequest, wValue, wIndex, None)

    def read(self, size):
        """Read from the CDC data endpoint"""
        assert self._locked

        return self.ep_data_in.read(size)

    def write(self, data):
        """Write to the CDC data endpoint"""
        assert self._locked

        self.ep_data_out.write(data)
