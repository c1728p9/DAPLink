import threading
import time
import usb.core

should_exit = False
global_start_time = time.time()


def _get_time():
    return time.time() - global_start_time


def rx_main(device, semaphore, rx_list):
    global should_exit
    try:
        while True:
            semaphore.acquire()
            data = device.read(0x81, 64, 10 * 1000)
            rx_list.append(data)
    finally:
        should_exit = True


def test_main(thread_index, device):
    global should_exit
    try:
        board_id = device.serial_number
        semaphore = threading.Semaphore(0)
        rx_list = []
        thread = threading.Thread(target=rx_main,
                                  args=(device, semaphore, rx_list))
        thread.setDaemon(True)
        thread.start()

        loop_count = 0
        while True:
            if loop_count % 1000 == 0:
                print("Thread %i loop %i at %s - %s board ID %s" %
                      (thread_index, loop_count, _get_time(), time.strftime("%H:%M:%S"), board_id))
            semaphore.release()
            data = bytearray(64)
            data[0] = 0x80
            device.write(0x01, data, 10 * 1000)
            while len(rx_list) == 0:
                pass
            resp = rx_list.pop(0)
            assert resp[0] == 0x80
            loop_count += 1
    except:
        print("Thread %i exception board %s" % (thread_index, board_id))
        raise
    finally:
        should_exit = True


def main():
    dev_list = usb.core.find(find_all=True, custom_match=_daplink_match)
    thread_list = []
    for index, dev in enumerate(dev_list):
        thread = threading.Thread(target=test_main, args=(index, dev))
        thread.setDaemon(True)
        thread.start()
        thread_list.append(thread)

    while not should_exit:
        time.sleep(1)


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


if __name__ == "__main__":
    main()
