from struct import unpack, calcsize
from pcapng import FileScanner
from collections import namedtuple
import logging
logging.basicConfig(level=logging.ERROR)

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

# Defined by pcapng - https://www.winpcap.org/ntar/draft/PCAP-DumpFileFormat.html
PCAPNG_BLOCK = {
    "INTERFACE_DESC": 0x00000001,
    "ENHANCED_PACKET": 0x00000006,
    "SECTION_HEADER": 0x0A0D0D0A
}


# Defines for this project


USB_TYPE = set([
    "Bulk",
    "Interrupt",
    "Control"
])
USB_DIR = set([
    "Setup",
    "In",
    "Out",
    "Status"
])
USBTransfer = namedtuple("USBTransfer", "bus, device, endpoint, type, dir, size_or_data")
FMT_CBW = "<IIIBBB"
SIZE_CBW = calcsize(FMT_CBW)
CBWTransfer = namedtuple("CBWTransfer", "signature, tag, data_transfer_length, flags, lun, length")
FMT_CSW = "<IIIB"
SIZE_CSW = calcsize(FMT_CSW)
CSWTransfer = namedtuple("CSWTransfer", "signature, tag, data_residue, status")
SCSITransfer = namedtuple("SCSITransfer", "cbw, csw, data")


def pcap_header_and_data(data):
    hdr = PcapHeader(*unpack(PCAP_HDR_FMT, data[:PCAP_HDR_SIZE]))
    return hdr, data[hdr.header_len:]


def pcap_to_usb(data):
    hdr = PcapHeader(*unpack(PCAP_HDR_FMT, data[:PCAP_HDR_SIZE]))
    contents = data[hdr.header_len:]
    ttype = PCAP_TRANSFER_TO_TYPE[hdr.transfer]
    if ttype == "Control":
        stage_num, = unpack("<B", data[PCAP_HDR_SIZE:PCAP_HDR_SIZE + 1])
        direction = NUM_TO_CONTROL_STAGE[stage_num]
    else:
        direction = "In" if hdr.endpoint & 0x80 else "Out"
    return USBTransfer(hdr.bus, hdr.device, hdr.endpoint & ~0x80, ttype, direction, data[hdr.header_len:])



PCAPNG_LINK = {
    249: pcap_to_usb
    #220:
}


def pcapng_to_usb_transfers(filename):
    with open(filename, "rb") as fp:
        scanner = FileScanner(fp)
        interfaces = None
        usb_transfers = []
        for block in scanner:
            if block.magic_number == PCAPNG_BLOCK["SECTION_HEADER"]:
                interfaces = []
            elif block.magic_number == PCAPNG_BLOCK["INTERFACE_DESC"]:
                print("Link type: %s" % block)
                if block.link_type in PCAPNG_LINK:
                    interfaces.append(PCAPNG_LINK[block.link_type])
                else:
                    log.error("Skipping interface!")
            elif block.magic_number == PCAPNG_BLOCK["ENHANCED_PACKET"]:
                usb_transfers.append(interfaces[block.interface_id](block.packet_data))
    return usb_transfers


def usb_to_scsi(xfers):
    cbw = None
    data = None
    xfer_itr = iter(xfers)
    scsi_list = []
    try:
        while True:

            cbw = None
            while cbw is None:
                xfer = xfer_itr.next()
                if xfer.dir != "Out":
                    log.error("Wrong CBW direction: %s", xfer.dir)
                    continue
                if len(xfer.size_or_data) != 31:
                    log.error("Wrong CBW size: %s", len(xfer.size_or_data))
                    continue
                if xfer.size_or_data[:4] != "USBC":
                    log.error("Wrong CBW signature: %s", xfer.size_or_data[:4])
                    continue
                cbw = CBWTransfer(*unpack(FMT_CBW, xfer.size_or_data[:SIZE_CBW]))

            data = None
            if cbw.data_transfer_length > 0:
                xfer = xfer_itr.next()
                direction = "In" if cbw.flags & (1 << 7) else "Out"
                if direction != xfer.dir:
                    log.error("Wrong direction in data stage - got %s, expected %s", xfer.dir, direction)
                data = xfer.size_or_data

            xfer = xfer_itr.next()
            if xfer.dir != "In":
                log.error("Wrong transfer direction in CSW stage: %s", xfer.dir)
            elif len(xfer.size_or_data) != 13:
                log.error("Wrong CSW packet size: %s" % len(xfer.size_or_data))
            csw = CSWTransfer(*unpack(FMT_CSW, xfer.size_or_data[:SIZE_CSW]))
            scsi_list.append(SCSITransfer(cbw, csw, data))
    except StopIteration:
        pass
    return scsi_list





def main():
    xfers = pcapng_to_usb_transfers("k64f_load.pcapng")
    scsis = usb_to_scsi(xfer for xfer in xfers if xfer.endpoint == 2 and xfer.device == 10)
    for scsi in scsis:
        print("%s %s" % (scsi.cbw, scsi.csw))
    # for xfer in xfers:
    #     if xfer.endpoint != 2:
    #         continue
    #     if xfer.device != 10:
    #         continue
    #     print(xfer)
    exit(0)
    with open('k64f_load.pcapng', 'rb') as fp:
        scanner = FileScanner(fp)
        blocks = list(scanner)
    block_types = {type(block) for block in blocks}
    function_set = set()
    interface_set = set()
    addr_sets = set()
    transfer_set = set()
    #link_type

    for block in (block for block in blocks if block.magic_number == 6):
        hdr = pcap_header(block.packet_data)
        function_set.add(hdr.function)
        interface_set.add(block.interface_id)
        addr_sets.add("%s.%s" % (hdr.device, hdr.endpoint))
        transfer_set.add(hdr.transfer)
    functions = sorted(list(function_set))
    #interfaces =
    functions_desc = [URB_FUNCTION_NUM_TO_STR[val] for val in functions]
    print("Transfers: %s" % sorted(list(transfer_set)))
    print("Addrs: %s" % sorted(list(addr_sets)))
    print("Interface set: %s" % interface_set)
    print("Used functions: %s" % functions_desc)
        #print("pcap header: %s" % (pcap_header(block.packet_data),))
    print("Function set: %s" % function_set)
    print("Block 1507: %s" % blocks[1507])
    print("Block types: %s" % block_types)
    print("There are %s blocks" % len(blocks))

#
# def find_daplink_usb(usb_sequence):
#
#     "USBC" - send
#     "USBS" - recv


if __name__ == "__main__":
    main()