from flask import jsonify
from time import sleep
from flask_socketio import send, emit

# Need this to support socketio decorators
# Docs say we need to import from __main__, but with gunicorn __name__ == 'main'
from main import socketio


def get_dummy_message(): 
    sleep(2)
    message = {"message": "Hello, this is a dummy message!"}
    return (jsonify(message), 200)


@socketio.on('json')
def handle_test_websocket_message(json):
    resp_json = {'message': 'This is a dummy response. Your message was: ' + json['message']}
    send(resp_json, json=True)
