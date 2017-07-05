#!/usr/bin/env python
import logging.config
from hmac import compare_digest

import hmac
from decouple import config
from flask import Flask, request, json

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
            'level': config('CONSOLE_LOGGING_LEVEL', default=logging.INFO),
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        }
    },
    'root': {
        'level': config('ROOT_LOGGING_LEVEL', default=logging.INFO),
    },
    'loggers': {
        'web': {
            'handlers': ['console'],
            'level': config('WEB_LOGGING_LEVEL', default=logging.INFO),
        },
        'facebook': {
            'handlers': ['console'],
            'level': config('FACEBOOK_LOGGING_LEVEL', default=logging.INFO),
        }
    }
}

logging.config.dictConfig(LOGGING)

FACEBOOK_SECRET = config('FACEBOOK_SECRET')
GREETING_TEXT = config('GREETING_TEXT')
VERIFICATION_TOKEN = config('FACEBOOK_VERIFICATION_TOKEN')
ACCESS_TOKEN = config('FACEBOOK_ACCESS_TOKEN')
DEBUG = config('DEBUG', cast=bool, default=False)
ENFORCE_ORIGIN = config('ENFORCE_ORIGIN', cast=bool, default=(not DEBUG))

app = Flask(__name__)
messenger = Messager(ACCESS_TOKEN)
logger = logging.getLogger('web.app')

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

    if not signature.startswith('sha1='):
        raise RuntimeError('Malformed signature')

    prefix, sha1_sig = signature.split('=')
    expected = hmac.new(FACEBOOK_SECRET.encode('ascii'),
                        request.data,
                        'sha1').hexdigest()

    if not compare_digest(sha1_sig, expected):
        if DEBUG:
            raise RuntimeError('Invalid SHA-1 signature, expected: {}, received: {}'.format(
                expected,
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
        logger.debug('Received a new message.')
        if ENFORCE_ORIGIN:
            assert_origin_from_facebook()
            logger.debug('Verified origin: Facebook')
        else:
            logger.warning('Verification for origin is not enforced!')

        raw_data = request.data.decode()
        data = json.loads(raw_data)
        logger.debug('Loaded {} amount of bytes from request.'.format(len(raw_data)))
        messages = Messager.unserialize_received_request('page', data)
        logger.debug('Unserialized {} messages.'.format(len(messages)))

        for message in messages:
            if message.type not in dispatchers:  # Ignore such a message.
                logger.warning('Ignored message type: {}'.format(message.type))
                continue

            # Let's be clear, dispatchers should only enqueue into task queues.
            # No complex and haunting work should be done here.
            dispatchers[message.type](message)

        logger.debug('Dispatched all messages through event processors.')
    except ValueError:
        logger.exception('While Facebook invoked the receive webhook, an exception occurred, malformed data.')
    except (KeyError, AttributeError):
        logger.exception('While Facebook invoked the receive webhook, an exception occurred, unexpected missing key.')
    except (RuntimeError, TypeError):
        logger.exception('While Facebook invoked the receive webhook, an exception occurred.')
    finally:
        # Don't unsubscribe, Facebook-chan.
        return 'OK'


if __name__ == '__main__':
    app.run(debug=True)
