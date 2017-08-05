from pcapng import FileScanner
from usbpcap import pcap_to_usb
from scsi import usb_to_scsi
import logging
logging.basicConfig(level=logging.ERROR)

log = logging.getLogger(__name__)


# Defined by pcapng - https://www.winpcap.org/ntar/draft/PCAP-DumpFileFormat.html
PCAPNG_BLOCK = {
    "INTERFACE_DESC": 0x00000001,
    "ENHANCED_PACKET": 0x00000006,
    "SECTION_HEADER": 0x0A0D0D0A
}


PCAPNG_LINK = {
    249: pcap_to_usb
    #220:
}


def pcapng_to_usb_transfers(filename):
    with open(filename, "rb") as fp:
        scanner = FileScanner(fp)
        interfaces = None
        index = None
        usb_transfers = []
        for block in scanner:
            if block.magic_number == PCAPNG_BLOCK["SECTION_HEADER"]:
                interfaces = []
                index = 1
            elif block.magic_number == PCAPNG_BLOCK["INTERFACE_DESC"]:
                print("Link type: %s" % block)
                if block.link_type in PCAPNG_LINK:
                    interfaces.append(PCAPNG_LINK[block.link_type])
                else:
                    log.error("Skipping interface!")
            elif block.magic_number == PCAPNG_BLOCK["ENHANCED_PACKET"]:
                usb_transfers.append(interfaces[block.interface_id](block.packet_data, index))
                index += 1
    return usb_transfers

