from thonny import launch, report_time
import webview
from thonny.flask_app.flask_app import startFlaskApp


report_time("Before launch")
launch()
# window = webview.create_window('MicroPython-Editor', 'https://innovator.educobot.com/tools/micropython-editor')
# webview.start()

# if __name__ == "__main__":
#     startFlaskApp()
#     window = webview.create_window('MicroPython-Editor', 'http://localhost:5000') 
#     webview.start()