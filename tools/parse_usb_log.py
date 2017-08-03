import json
from struct import unpack, calcsize
from pcapng import FileScanner
from collections import namedtuple

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

def safe_list(obj):
    new_list = []
    itr = iter(obj)
    try:
        while True:
            try:
                print("Looping")
                new_list.append(itr.next())
            except ValueError:
                print("Value error")
                pass
    except StopIteration:
        print("Stop iteration")
        pass

    return new_list
#USB pcap format - http://desowin.org/usbpcap/captureformat.html


PCAP_HDR_FMT = "<HQIHBHHBBI"
PCAP_HDR_SIZE = calcsize(PCAP_HDR_FMT)
PcapHeader = namedtuple("PcapHeader", "header_len, irq_id, status, function,"
                        "info, bus, device, endpoint, transfer, data_length")

def pcap_header(data):
    return PcapHeader(*unpack(PCAP_HDR_FMT, data[:PCAP_HDR_SIZE]))


def main():
    with open('k64f_load.pcapng', 'rb') as fp:
    #with open('usblog_2124.pcapng', 'rb') as fp:

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
        #for block in blocks:
        #    print("Block %s" % block)
    with open('k64f_load.json') as data_file:
        data = json.load(data_file)
    last_num = None
    changes = []
    for entry in data:
        num = int(entry["_source"]["layers"]["frame"]["frame.number"])
        if last_num is None or last_num + 1 != num:
            changes.append((last_num, num))
        last_num = num

    print("Last number %s" % last_num)
    print("There are %s changes" % len(changes))
    for old, new in changes:
        print("%s -> %s" % (old, new))

    #
    # "_source": {
    #     "layers": {
    #         "frame": {
    #             "frame.interface_id": "0",
    #             "frame.encap_type": "152",
    #             "frame.time": "Aug  2, 2017 09:23:56.319101000 GMT Daylight Time",
    #             "frame.offset_shift": "0.000000000",
    #             "frame.time_epoch": "1501662236.319101000",
    #             "frame.time_delta": "0.008002000",
    #             "frame.time_delta_displayed": "0.008002000",
    #             "frame.time_relative": "3.411886000",
    #             "frame.number": "51",


if __name__ == "__main__":
    main()