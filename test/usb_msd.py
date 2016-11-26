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

import struct
import numbers
import usb.util


class USBMsd(object):

    # Bulk only transport documented in
    #     "Universal Serial Bus Mass Storage Class"
    # SCSI commands documented in "SCSI Commands Reference Manual" by Seagate

    CLASS_MSD = 0x8
    # Write 10
    # Read 10
    # Test unit ready
    # Request Sense

    # dCBWSignature
    # dCBWTag
    # dCBWDataTransferLength
    # bmCBWFlags
    # bCBWLUN
    # bCBWCBLength
    FMT_CBW = "<IIIBBB"

    # dCSWSignature
    # dCSWTag
    # dCSWDataResidue
    # bCSWStatus
    FMT_CSW = "<IIIB"

    CSW_STATUS_PASSED = 0
    CSW_STATUS_FAILED = 1
    CSW_STATUS_PHASE_ERROR = 2

    # Some SCSI commands
    # Value   Keil middleware define         Seagate name
    # 0x12    SCSI_INQUIRY                   INQUIRY
    # 0x23    SCSI_READ_FORMAT_CAPACITIES    Missing
    # 0x25    SCSI_READ_CAPACITY             READ CAPACITY (10)
    # 0x28    SCSI_READ10                    READ (10)
    # 0x1A    SCSI_MODE_SENSE6               MODE SENSE (6)
    # 0x00    SCSI_TEST_UNIT_READY           TEST UNIT READY
    # 0x2A    SCSI_WRITE10                   WRITE (10)
    # 0x03    SCSI_REQUEST_SENSE             REQUEST SENSE
    # 0x1E    SCSI_MEDIA_REMOVAL             Missing

    def __init__(self, device):
        self._dev = device
        self._if = None
        self._ep_in = None
        self._ep_out = None
        self._locked = False
        self._cbw_tag = 0

        # Find interface
        for interface in device.get_active_configuration():
            if interface.bInterfaceClass == USBMsd.CLASS_MSD:
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
        assert self._ep_out is not None

    def lock(self):
        """Acquire exclisive access to MSD"""
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
        """Release exclusive access to MSD"""
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

    def scsi_read10(self, lba, block_count):
        """Send the SCSI read 10 command and return the data read"""
        block_size = 512

        cbwcb = bytearray(10)
        cbwcb[0] = 0x28
        cbwcb[2] = (lba >> (8 * 3)) & 0xFF
        cbwcb[3] = (lba >> (8 * 2)) & 0xFF
        cbwcb[4] = (lba >> (8 * 1)) & 0xFF
        cbwcb[5] = (lba >> (8 * 0)) & 0xFF
        cbwcb[7] = (block_count >> (8 * 1)) & 0xFF
        cbwcb[8] = (block_count >> (8 * 0)) & 0xFF
        ret, data = self._msd_transfer(cbwcb, 0, block_count * block_size)
        assert ret == self.CSW_STATUS_PASSED
        return data

    def _msd_transfer(self, cbwcb, lun, size_or_data=None):
        """Perform a bulk only transfer"""
        assert self._locked
        assert 1 <= len(cbwcb) <= 16

        # Increment packet tag
        transfer_tag = self._cbw_tag
        self._cbw_tag = (self._cbw_tag + 1) & 0xFFFFFFFF

        # None means data size of zero
        if size_or_data is None:
            size_or_data = 0

        in_transfer = isinstance(size_or_data, numbers.Number)
        transfer_size = (size_or_data if in_transfer else len(size_or_data))
        assert in_transfer or len(size_or_data) > 0

        # Phase - Command transport
        dCBWSignature = 0x43425355
        dCBWTag = transfer_tag
        dCBWDataTransferLength = transfer_size
        bmCBWFlags = (1 << 7) if in_transfer else 0
        bCBWLUN = lun
        bCBWCBLength = len(cbwcb)
        params = [dCBWSignature, dCBWTag, dCBWDataTransferLength,
                  bmCBWFlags, bCBWLUN, bCBWCBLength]
        cbw = struct.pack(self.FMT_CBW, *params)
        pad_size = 16 - len(cbwcb)
        payload = cbw + cbwcb + bytearray(pad_size)
        self._ep_out.write(payload)

        # Phase - Data Out or Data In (Optional)
        if transfer_size > 0:
            if in_transfer:
                data = self._ep_in.read(transfer_size)
            else:
                data = None
                self._ep_out.write(size_or_data)

        # Phase - Status Transport
        csw = self._ep_in.read(13)
        dCSWSignature, dCSWTag, dCSWDataResidue, bCSWStatus = \
            struct.unpack(self.FMT_CSW, csw)
        assert dCSWSignature == 0x53425355
        assert dCSWTag == transfer_tag
        #TODO - check residue
        return (bCSWStatus, data)
