import webview
from threading import Thread
class Api():
    def log(self, value):
        print(value)

    def deploy(self, value):
        print(value)
        return value

def startWebview():
    window = webview.create_window('MicroPython-Editor', 'http://localhost:5000', js_api=Api())
    webviewThread = Thread(target=webview.start)
    webviewThread.daemon = True
    webviewThread.start()
    return window

def closeWebview(window):
    window.close()
    webview.stop()

if __name__ == "__main__":
    window = webview.create_window('MicroPython-Editor', 'http://localhost:5000', js_api=Api())
    webview.start()