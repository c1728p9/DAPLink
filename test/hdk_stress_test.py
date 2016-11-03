import mbed_lstools
import threading
import time
import os
import serial

lstools = mbed_lstools.create()

should_exit = False


def msd_remount_main(target_id):
    pass


def msd_throughput_main(mount_point):
    file_path = mount_point + "/" + "dummy.txt"
    data = "T" * 32 * 1024 * 10# * 1024
    while not should_exit:
        print("Writing to %s" % file_path)
        pass
        with open(file_path, "wb") as f:
            f.write(data)
        os.remove(file_path)


def cdc_throughput_main(serial_port):
    ser = serial.Serial(serial_port)  # open serial port
    while not should_exit:
        print("Using serial port %s" % serial_port)
        ser.baudrate = 115200
        ser.write("this is test data")
        ser.baudrate = 9600
        ser.write("more test data")
    ser.close()


mbed_list = lstools.list_mbeds()
thread_list = []
for mbed in mbed_list:
    mbed_unique_id = mbed['target_id']
    mbed_serial_port = mbed['serial_port']
    mbed_mount_point = mbed['mount_point']
    msd_thread = threading.Thread(target=msd_throughput_main,
                                  args=(mbed_mount_point,))
    cdc_thread = threading.Thread(target=cdc_throughput_main,
                                  args=(mbed_serial_port,))
    thread_list.append(msd_thread)
    thread_list.append(cdc_thread)
    msd_thread.start()
    cdc_thread.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
should_exit = True

for thread in thread_list:
    thread.join()
