from thonny import launch, report_time
from thonny.flask_app import startFlaskApp
from thonny.login_validator import openLoginScreen, LoginApp

def main():
    startFlaskApp()
    report_time("Before launch")
    launch()

loginApp = LoginApp()
print(loginApp.isLoggedIn())    
if loginApp.isLoggedIn():
    main()
else:
    openLoginScreen(successFunction=main)

# window = webview.create_window('MicroPython-Editor', 'https://innovator.educobot.com/tools/micropython-editor')
# webview.start()

# if __name__ == "__main__":
#     window = webview.create_window('MicroPython-Editor', 'http://localhost:5000') 
#     webview.start()