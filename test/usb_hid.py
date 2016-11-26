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


class USBHid(object):

    # HID commands documented in
    # Device Class Definition for Human Interface Devices (HID)

    CLASS_HID = 0x3

    DESC_TYPE_HID = 0x21
    DESC_TYPE_REPORT = 0x22
    DESC_TYPE_PHYSICAL = 0x23

    REPORT_TYPE_INPUT = 1
    REPORT_TYPE_OUTPUT = 2
    REPORT_TYPE_FEATURE = 3

    def __init__(self, device):
        self._dev = device
        self._if = None
        self._ep_in = None
        self._ep_out = None
        self._locked = False

        # Find interface
        for interface in device.get_active_configuration():
            if interface.bInterfaceClass == USBHid.CLASS_HID:
                assert self._if is None
                self._if = interface
        assert self._if is not None

        # Find endpoints
        for endpoint in self._if:
            if endpoint.bEndpointAddress & 0x80:
                assert self._ep_in is None
                self._ep_in = endpoint
            else:
                assert self._ep_out is None
                self._ep_out = endpoint
        assert self._ep_in is not None
        # Endpoint out can be None

    def lock(self):
        """Acquire exclisive access to HID"""
        assert not self._locked

        num = self._if.bInterfaceNumber
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
        """Release exclusive access to HID"""
        assert self._locked

        num = self._if.bInterfaceNumber
        usb.util.release_interface(self._dev, num)
        try:
            self._dev.attach_kernel_driver(num)
        except NotImplementedError:
            pass
        except usb.core.USBError:
            pass
        self._locked = False

    def set_idle(self, report_id=0, duration=0):
        """Send a HID Set_Idle request"""
        assert self._locked
        assert report_id & ~0xFF == 0
        assert duration & ~0xFF == 0

        bmRequestType = 0x21
        bmRequest = 0x0A                        # SET_IDLE
        wValue = ((duration << 8) |
                  (report_id << 0))             # Report and duration
        wIndex = self._if.bInterfaceNumber      # HID interface
        self._dev.ctrl_transfer(bmRequestType, bmRequest, wValue, wIndex, None)

    def get_descriptor(self, desc_type, index):
        """Get the given descriptor"""
        assert self._locked
        assert desc_type & ~0xFF == 0
        assert index & ~0xFF == 0

        bmRequestType = 0x81
        bmRequest = 0x6                             # GET_DESCRIPTOR
        wValue = (((index & 0xFF) << (0 * 8)) |
                  ((desc_type & 0xFF) << (1 * 8)))  # Descriptor type and index
        wIndex = self._if.bInterfaceNumber          # HID interface
        return self._dev.ctrl_transfer(bmRequestType, bmRequest,
                                       wValue, wIndex, 256)

    def set_report_req(self, data, report_type=REPORT_TYPE_OUTPUT,
                       report_id=0):
        """Set a report of the given type"""
        assert self._locked
        assert report_type & ~0xFF == 0
        assert report_id & ~0xFF == 0

        bmRequestType = 0x21
        bmRequest = 0x09                        # SET_REPORT
        wValue = ((report_type << 8) |
                  (report_id << 0))             # Report and duration
        wIndex = self._if.bInterfaceNumber      # HID interface
        self._dev.ctrl_transfer(bmRequestType, bmRequest, wValue, wIndex, data)

    def set_report(self, data):
        """Send report to the device"""
        assert self._locked

        if self._ep_out is None:
            self.set_report_req(data)
        else:
            self._ep_out.write(data)

    def get_report(self, size):
        """Read report from the device"""
        assert self._locked

        return self._ep_in.read(size)
