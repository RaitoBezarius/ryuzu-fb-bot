#!/usr/bin/env python
from decouple import config
from flask import Flask, request

app = Flask(__name__)

VERIFICATION_TOKEN = config('FACEBOOK_VERIFICATION_TOKEN')


@app.route('/callback', methods=["GET"])
def fb_webhook() -> str:
    verify_token = request.args.get('hub.verify_token')
    if verify_token == VERIFICATION_TOKEN:
        return request.args.get('hub.challenge')
    else:
        return "Wrong verification token!"


if __name__ == '__main__':
    app.run(debug=True)
