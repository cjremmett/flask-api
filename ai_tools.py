from flask import jsonify


def get_dummy_message(): 
    message = {"message": "Hello, this is a dummy message!"}
    return (jsonify(message), 200)