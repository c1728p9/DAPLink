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

import os
import usb.core
import functools
import threading
import test_info
from usb_cdc import USBCdc
from usb_hid import USBHid
from usb_msd import USBMsd


def test_usb(workspace, parent_test, force=False):
    """Run raw USB tests

    Requirements:
        -daplink-validation must be loaded for the target.
    """
    if not _platform_supports_usb_test() and not force:
        parent_test.info("Skipping USB test on this platform")
        return

    # Find the device under test
    test_info = parent_test.create_subtest("USB test")
    serial_number = workspace.board.get_unique_id()
    dev = _daplink_from_serial_number(serial_number)
    if dev is None:
        test_info.failure("Could not find board with serial number %s" %
                          serial_number)
        return

    # Acquire exclusive access to interfaces
    cdc = USBCdc(dev)
    hid = USBHid(dev)
    msd = USBMsd(dev)
    cdc.lock()
    hid.lock()
    msd.lock()

#    cdc.set_line_coding(115200)
#    while True:
#        raw_input("Press any key to continue")
#        cdc.get_line_coding()

    _set_usb_test_mode(hid, False)

    #TODO - TEST 256 BYTE CONTROL IN TANSFER!!!!

    # Test CDC
    cdc.set_line_coding(115200)
    baud, fmt, parity, databits = cdc.get_line_coding()
    print("Baud %i, fmt %i, parity %i, databits %i" %
          (baud, fmt, parity, databits))
    cdc.send_break(cdc.SEND_BREAK_ON)
    cdc.send_break(cdc.SEND_BREAK_OFF)
    data = cdc.read(1024)
    print("Serial port data: %s" % bytearray(data))
    cdc.write("Hello world")
    data = cdc.read(1024)
    print("Serial port data2: %s" % bytearray(data))

    # Test HID
    hid.set_idle()
    #TODO - descriptors should probably be enumerated
    report = hid.get_descriptor(hid.DESC_TYPE_REPORT, 0)
    print("Report descriptor: %s" % report)
    # Send CMSIS-DAP vendor command to get the serial number
    data = bytearray(64)
    data[0] = 0x80
    hid.set_report(data)
    resp = hid.get_report(64)
    length = resp[1]
    print("CMSIS-DAP response: %s" %
          bytearray(resp[1:1 + length]).decode("utf-8"))

    # Test MSC
    data = msd.scsi_read10(0, 1)
    print("MBR[0:16]: %s" % data[0:16])

    # Test various patterns of control transfers
    #
    # Some devices have had problems with back-to-back
    # control transfers. Intentionally send these sequences
    # to make sure they are properly handled.
    for _ in range(100):
        # Control transfer with a data in stage
        cdc.get_line_coding()
    for _ in range(100):
        # Control transfer with a data out stage followed
        # by a control transfer with a data in stage
        cdc.set_line_coding(115200)
        cdc.get_line_coding()
    for _ in range(100):
        # Control transfer with a data out stage
        cdc.set_line_coding(115200)

    cdc.ep_data_out.clear_halt()
    cdc.ep_data_out.write('')      # DATA0
    cdc.ep_data_out.clear_halt()
    cdc.ep_data_out.write('')      # DATA0

    cdc.ep_data_out.clear_halt()
    cdc.ep_data_out.write('')      # DATA 0
    cdc.ep_data_out.write('')      # DATA 1
    cdc.ep_data_out.clear_halt()
    cdc.ep_data_out.write('')      # DATA 0

#    data = bytearray(64)
#    data[0] = 0x88
#    data[1] = 0
#    hid.set_report(data)
#    resp = hid.get_report(64)
#    if (resp[0] != 0x88) or (resp[1] != 1):
#        print("Error disabling USB test mode")


#    for _ in range(1):
    msd_data = 'x' * 512 * 1
    msd.scsi_write10(100, msd_data)

    def _test_msd():
        print("msd started")
        for _ in range(50):
            #msd.scsi_read10(100, 1000)
            msd_data = 'x' * 1024 * 1024 # 1 MB
            msd.scsi_write10(100, msd_data)
        print("msd end")

    def _test_cdc():
        print("cdc started")
        for _ in range(10000):
            #cdc.set_line_coding(115200)
            cdc.get_line_coding()
            #cdc.send_break(cdc.SEND_BREAK_ON)
            #cdc.send_break(cdc.SEND_BREAK_OFF)
#            data = cdc.read(1024)
#            cdc.write("Hello world")
#            data = cdc.read(1024)
        print("cdc end")

    thread = threading.Thread(target=_test_msd)
    thread2 = threading.Thread(target=_test_cdc)
    thread.start()
    thread2.start()
    print("main start")
    data = bytearray(64)
    data[0] = 0x80
    for _ in range(10000):
        hid.set_report(data)
        hid.get_report(64)

#    for _ in range(100):
#        # Control transfer with a data in stage
#        cdc.get_line_coding()
#    for _ in range(100):
#        # Control transfer with a data out stage followed
#        # by a control transfer with a data in stage
#        cdc.set_line_coding(115200)
#        cdc.get_line_coding()
#    for _ in range(100):
#        # Control transfer with a data out stage
#        cdc.set_line_coding(115200)
    print("main end")

    thread.join()
    thread2.join()

    _set_usb_test_mode(hid, False)

    cdc.unlock()
    hid.unlock()
    msd.unlock()


def _daplink_match(dev):
    """DAPLink match function to be used with usb.core.find"""
    try:
        device_string = dev.product
    except ValueError:
        return False
    if device_string is None:
        return False
    if device_string.find("CMSIS-DAP") < 0:
        return False
    return True


def _daplink_from_serial_number(serial_number):
    """Return a usb handle to the DAPLink device with the serial number"""
    dev_list = usb.core.find(find_all=True, custom_match=_daplink_match)
    for dev in dev_list:
        if dev.serial_number == serial_number:
            return dev
    return None


def _platform_supports_usb_test():
    """Return True if this platform supports USB testing, False otherwise"""
    if os.name != "posix":
        return False
    if os.uname()[0] == "Darwin":
        return False
    return True


def _set_usb_test_mode(hid, enabled):
    data = bytearray(64)
    data[0] = 0x88
    data[1] = 1 if enabled else 0
    hid.set_report(data)
    resp = hid.get_report(64)
    if (resp[0] != 0x88) or (resp[1] != 1):
        print("Error configuring USB test mode")
    else:
        print("HID returned %s" % resp)

def main():

    class Dummy(object):
        pass

    def get_unique_id(unique_id):
        return unique_id

    dev_list = usb.core.find(find_all=True, custom_match=_daplink_match)
    for dev in dev_list:
        board_id = dev.serial_number
        print("Testing board %s" % board_id)
        print("----------------")
        d = Dummy()
        d.board = Dummy()
        d.board.unique_id = dev.serial_number
        d.board.get_unique_id = functools.partial(get_unique_id,
                                                  board_id)
        test_usb(d, test_info.TestInfoStub(), True)


if __name__ == "__main__":
    main()
