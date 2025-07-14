import serial, time

ser = serial.Serial('/dev/ttyACM1', 115200, timeout=1)
time.sleep(0.1)  # give the port a moment
ser.write(b'conf can on')
print("Reply to 'conf can on':", ser.readline())
ser.write(b'can on')
print("Reply to 'can on':", ser.readline())
ser.close()