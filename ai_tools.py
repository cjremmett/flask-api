from flask import jsonify
from time import sleep


def get_dummy_message(): 
    sleep(2)
    message = {"message": "Hello, this is a dummy message!"}
    return (jsonify(message), 200)