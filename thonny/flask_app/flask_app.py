from flask import Flask, request, jsonify, render_template
from threading import Thread

FlaskAPP =Flask(__name__, static_folder='./static', template_folder='./templates')

from flask_cors import CORS
CORS(FlaskAPP, resources={r"/*": {"origins": "*"}})

@FlaskAPP.route('/', methods=['GET'])
def home():
    return render_template("index.html")

@FlaskAPP.route('/deploy', methods=['POST'])
def deploy():
    data = request.get_json()
    return jsonify(data)




def startFlaskApp():
    flask_thread = Thread(target=FlaskAPP.run, kwargs={'use_reloader': False})
    flask_thread.daemon = True
    flask_thread.start()

if __name__ == '__main__':
    FlaskAPP.run(debug=True)