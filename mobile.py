from machine import Pin

import time
import machine
from machine import Pin
led2 = Pin(2, Pin.OUT)
while True:
  print("print called")
  led2.value(1)
  time.sleep(1)
  led2.value(1)
  time.sleep(1)