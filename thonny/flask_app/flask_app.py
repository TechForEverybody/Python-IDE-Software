from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from threading import Thread
from thonny import get_runner, get_workbench, ui_utils


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

def run_app():
    FlaskAPP.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)



def startFlaskApp():
    flask_thread = Thread(target=run_app)
    flask_thread.daemon = True
    flask_thread.start()

if __name__ == '__main__':
    FlaskAPP.run(debug=True)