from thonny import launch, report_time
from thonny.flask_app.flask_app import startFlaskApp
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
