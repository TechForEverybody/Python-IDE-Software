import network
import time
import webrepl

def do_connect():
    wifi_ssid = "Smart Car"
    wifi_password = "12345678" 
    station = network.WLAN(network.AP_IF)
    station.active(True)
    while station.active() == False:
        print("Connecting...")
        time.sleep(3)
    print("Connected!")
    print("My IP Address:", station.ifconfig()[0])
if __name__ == "__main__":
    do_connect()
    webrepl.start()