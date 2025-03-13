import webview
from threading import Thread
class Api():
    def log(self, value):
        print(value)

    def deploy(self, value):
        print(value)
        return value



def _startWebview():
    window = webview.create_window('MicroPython-Editor', 'http://localhost:5000', js_api=Api())
    webview.start()
def startWebview():
    webviewThread = Thread(target=_startWebview)
    webviewThread.daemon = True
    webviewThread.start()

def closeWebview(window):
    
    window.close()
    webview.stop()

if __name__ == "__main__":
    # window = webview.create_window('MicroPython-Editor', 'http://localhost:5000', js_api=Api())
    # webview.start()
    startWebview()