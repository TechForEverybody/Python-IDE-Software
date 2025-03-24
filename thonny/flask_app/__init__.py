from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from threading import Thread
from thonny import get_runner, get_workbench, get_shell


FlaskAPP =Flask(__name__, static_folder='./static', template_folder='./templates')

CORS(FlaskAPP, resources={r"/*": {"origins": "*"}})

@FlaskAPP.route('/', methods=['GET'])
def home():
    return render_template("index.html")

@FlaskAPP.route('/api/v1/esp32/deploy', methods=['POST'])
def deploy():
    data = request.get_json()
    code = data['data']
    get_workbench().get_editor_notebook().get_current_editor().get_code_view().set_content(code)
    get_runner().cmd_run_current_script()
    return jsonify({
        'status': 'success',
        'message': 'Reached to IDE successfully'
    })

@FlaskAPP.route('/ide/shell/get/messages', methods=['GET'])
def get_shell_messages():
    messages=get_shell().text.get("1.0", "end-1c")
    # print(messages)
    return jsonify({
        'status': 'success',
        'messages': messages
    })

@FlaskAPP.route('/ide/shell/restart-backend', methods=['GET'])
def restart_shell():
    get_runner().restart_backend(clean=True)
    return jsonify({
        'status': 'success',
        'message': 'Shell restarted successfully'
    })

@FlaskAPP.route('/ide/shell/save-in-persistent-storage', methods=['POST'])
def save_in_persistent_storage():
    data = request.get_json()
    code = data['data']
    code = code.replace("\"", "\\\"")
    new_code = f"""bootPyContent = \"\"\"# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
import program
\"\"\"

code = \"\"\"{code}\"\"\"

with open("boot.py", "w") as f:
    f.write(bootPyContent)
with open("program.py", "w") as f:
    f.write(code)"""
    get_workbench().get_editor_notebook().get_current_editor().get_code_view().set_content(new_code)
    get_runner().cmd_run_current_script()
    print(new_code)
    return jsonify({
        'status': 'success',
        'message': 'Code saved in persistent storage successfully'
    })
def run_app():
    FlaskAPP.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)



def startFlaskApp():
    flask_thread = Thread(target=run_app)
    flask_thread.daemon = True
    flask_thread.start()

if __name__ == '__main__':
    FlaskAPP.run(debug=True)



