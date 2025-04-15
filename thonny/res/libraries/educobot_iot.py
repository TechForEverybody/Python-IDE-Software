import urequests
import ujson
import network
import time
import machine
class eduCOBOT_IOT:
    def __init__(self,secretKey,APIKey,wifiName='eduCOBOT',wifiPassword='1234554322'):
        self.IndicatorPin = machine.Pin(2, machine.Pin.OUT)
        self.secretKey = secretKey
        self.APIKey = APIKey
        self.wifiName = wifiName
        self.wifiPassword = wifiPassword
        self.isVerified = False
        self.wlan = network.WLAN(network.STA_IF)
        self.machineURL = 'http://machine.server.iot.educobot.com'
        self.connectToWiFi()
        self.validateProject()
        self.IPAddress='0.0.0.0'
    def connectToWiFi(self):
        self.wlan.active(True)
        print('Attempting to connect to the network...')
        self.wlan.connect(self.wifiName, self.wifiPassword)        
        max_wait = 10
        while max_wait > 0 and not self.wlan.isconnected():
            max_wait -= 1
            print('waiting for connection...')
            time.sleep(1)
        if not self.wlan.isconnected():
            print('Network Connection has failed')
        else:
            print('Connected to the network successfully.')
            self.IndicatorPin.value(1)
            time.sleep(0.2)
            self.IndicatorPin.value(0)
            time.sleep(0.2)
            self.IndicatorPin.value(1)
            time.sleep(0.2)
            self.IndicatorPin.value(0)
            status = self.wlan.ifconfig()
            print( 'Assigned Local IP = ' + status[0] )
            self.IPAddress=status[0]
    def validateProject(self):
        print('verifying project....')
        try:
            response = urequests.post(
                url=self.machineURL+'/VerifyHardwareProjectAPI',
                headers = {'content-type': 'application/json'},
                data=ujson.dumps({'secretKey':self.secretKey,'APIKey':self.APIKey})
                )
            json=response.json()
            if(json['success']==True):
                print(json['message'])
                self.isVerified = True
                self.IndicatorPin.value(1)
            else:
                print(json['message'])
        except Exception as e:
            print(e)
            print('Project verification failed')
    def sendData(self,variableName,variableValue):
        if(self.isVerified):
            try:
                response = urequests.post(
                    url=self.machineURL+'/ChangeVariableValueAPI',
                    headers = {'content-type': 'application/json'},
                    data=ujson.dumps({'secretKey':self.secretKey,'APIKey':self.APIKey,'variableName':variableName,'variableValue':variableValue})
                    )
                json=response.json()
                if(json['success']==True):
                    print('Data sent successfully')
                else:print(json['message'])
            except Exception as e:
                print(e)
                pass
        else:
            print('Project not verified')
    def readData(self,variableName):
        if(self.isVerified):
            try:
                response = urequests.post(
                    url=self.machineURL+'/GetVariableValueAPI',
                    headers = {'content-type': 'application/json'},
                    data=ujson.dumps({'secretKey':self.secretKey,'APIKey':self.APIKey,'variableName':variableName})
                    )
                json=response.json()
                if(json['success']==True):
                    return json['data']['value']
                else:
                    return None
            except Exception as e:
                print(e)
                return None
        else:
            print('Project not verified')
            return None

