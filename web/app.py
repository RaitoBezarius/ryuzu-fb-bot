#!/usr/bin/env python
import logging.config
from hmac import compare_digest

import hashlib
from decouple import config
from flask import Flask, request, json, abort

from facebook.messager import Messager, FacebookMessage, FacebookMessageType

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
        },
        'simple': {
            'format': '[%(levelname)s][%(asctime)s] %(module)s: %(message)s'
        }
    },
    'handlers': {
        'console': {
            'level': config('CONSOLE_LOGGING_LEVEL', default='INFO'),
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        }
    },
    'loggers': {
        'web': {
            'handlers': ['console'],
            'level': config('WEB_LOGGING_LEVEL', default='INFO'),
        },
        'facebook': {
            'handlers': ['console'],
            'level': config('FACEBOOK_LOGGING_LEVEL', default='INFO')
        }
    }
}

logging.config.dictConfig(LOGGING)

FACEBOOK_SECRET = config('FACEBOOK_SECRET')
GREETING_TEXT = config('GREETING_TEXT')
FB_SHA1_SIGNATURE = hashlib.sha1(FACEBOOK_SECRET.encode('ascii')).hexdigest()
VERIFICATION_TOKEN = config('FACEBOOK_VERIFICATION_TOKEN')
ACCESS_TOKEN = config('FACEBOOK_ACCESS_TOKEN')
DEBUG = config('DEBUG', default=False)

app = Flask(__name__)
messenger = Messager(ACCESS_TOKEN)
logger = logging.getLogger(__name__)

# Announcing classification: Initial-Y Series 01, "One Who Follows", RyuZU.
messenger.subscribe_to_page()
messenger.set_greeting_text(GREETING_TEXT)


def process_postback_message(message: FacebookMessage):
    logger.info('Received postback.')


def process_received_message(message: FacebookMessage):
    logger.info('Received message: {}'.format(
        message.text
    ))


dispatchers = {
    FacebookMessageType.postback: process_postback_message,
    FacebookMessageType.received: process_received_message,
}


def assert_origin_from_facebook():
    signature = request.headers.get('X-Hub-Signature', None)

    if not signature:
        raise RuntimeError('Invalid origin')

    prefix, sha1_sig = signature.split('=')

    if not compare_digest(sha1_sig, FB_SHA1_SIGNATURE):
        if DEBUG:
            raise RuntimeError('Invalid SHA-1 signature, expected: {}, received: {}'.format(
                FB_SHA1_SIGNATURE,
                sha1_sig))
        else:
            raise RuntimeError('Invalid SHA-1 signature')


@app.route('/callback', methods=["GET"])
def fb_verify_webhook() -> str:
    verify_token = request.args.get('hub.verify_token')
    if verify_token == VERIFICATION_TOKEN:
        return request.args.get('hub.challenge')
    else:
        return "Wrong verification token!"


@app.route('/callback', methods=["POST"])
def fb_receive_message_webhook() -> str:
    try:
        assert_origin_from_facebook()
        data = json.loads(request.data.decode())
        messages = Messager.unserialize_received_request('page', data)

        for message in messages:
            if message.type not in dispatchers:  # Ignore such a message.
                logger.info('Ignored message type: {}'.format(message.type))
                continue

            dispatchers[message.type](message)

        return 'OK'
    except RuntimeError:
        logger.exception('While Facebook invoked the receive webhook, an exception occurred.')
        abort(400)


if __name__ == '__main__':
    app.run(debug=True)
