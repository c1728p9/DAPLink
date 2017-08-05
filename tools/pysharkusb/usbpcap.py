from struct import unpack, calcsize
from collections import namedtuple
from common import USBTransfer
import logging

log = logging.getLogger(__name__)

# Defined by Windows
URB_FUNCTION = {
    "URB_FUNCTION_SELECT_CONFIGURATION": 0x0000,
    "URB_FUNCTION_SELECT_INTERFACE": 0x0001,
    "URB_FUNCTION_ABORT_PIPE": 0x0002,
    "URB_FUNCTION_TAKE_FRAME_LENGTH_CONTROL": 0x0003,
    "URB_FUNCTION_RELEASE_FRAME_LENGTH_CONTROL": 0x0004,
    "URB_FUNCTION_GET_FRAME_LENGTH": 0x0005,
    "URB_FUNCTION_SET_FRAME_LENGTH": 0x0006,
    "URB_FUNCTION_GET_CURRENT_FRAME_NUMBER": 0x0007,
    "URB_FUNCTION_CONTROL_TRANSFER": 0x0008,
    "URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER": 0x0009,
    "URB_FUNCTION_ISOCH_TRANSFER": 0x000A,
    "URB_FUNCTION_GET_DESCRIPTOR_FROM_DEVICE": 0x000B,
    "URB_FUNCTION_CLASS_INTERFACE": 0x001B,
    "URB_FUNCTION_RESET_PIPE": 0x001E,
    "URB_FUNCTION_GET_DESCRIPTOR_FROM_INTERFACE": 0x0028,
}
URB_FUNCTION_NUM_TO_STR = dict((value, key) for key, value in URB_FUNCTION.iteritems())

# Defined by USBPCAP - http://desowin.org/usbpcap/captureformat.html
PCAP_HDR_FMT = "<HQIHBHHBBI"
PCAP_HDR_SIZE = calcsize(PCAP_HDR_FMT)
PcapHeader = namedtuple("PcapHeader", "header_len, irq_id, status, function,"
                                      "info, bus, device, endpoint, transfer, data_length")

PCAP_CONTROL_STAGE = {
    "Setup": 0,
    "Data": 1,
    "Status": 2
}
NUM_TO_CONTROL_STAGE = dict((value, key) for key, value in PCAP_CONTROL_STAGE.iteritems())
PCAP_TRANSFER_TO_TYPE = {
    0: "Isochronous",
    1: "Interrupt",
    2: "Control",
    3: "Bulk"
}


def pcap_to_usb(data, packet_id):
    hdr = PcapHeader(*unpack(PCAP_HDR_FMT, data[:PCAP_HDR_SIZE]))
    ttype = PCAP_TRANSFER_TO_TYPE[hdr.transfer]
    if ttype == "Control":
        stage_num, = unpack("<B", data[PCAP_HDR_SIZE:PCAP_HDR_SIZE + 1])
        direction = NUM_TO_CONTROL_STAGE[stage_num]
    else:
        direction = "In" if hdr.endpoint & 0x80 else "Out"
    return USBTransfer(packet_id, None, None, hdr.bus, hdr.device,
                       hdr.endpoint & ~0x80, ttype, direction,
                       data[hdr.header_len:])
