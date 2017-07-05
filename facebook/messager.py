# -*- coding: utf8 -*-
import json
import logging
from enum import Enum
from typing import List, Dict, Any, NamedTuple, Optional

import requests

__original_author__ = "enginebai"

logger = logging.getLogger(__name__)

# send message fields
RECIPIENT_FIELD = "recipient"
MESSAGE_FIELD = "message"
ATTACHMENT_FIELD = "attachment"
TYPE_FIELD = "type"
TEMPLATE_TYPE_FIELD = "template_type"
TEXT_FIELD = "text"
TITLE_FIELD = "title"
SUBTITLE_FIELD = "subtitle"
IMAGE_FIELD = "image_url"
BUTTONS_FIELD = "buttons"
PAYLOAD_FIELD = "payload"
URL_FIELD = "url"
ELEMENTS_FIELD = "elements"
QUICK_REPLIES_FIELD = "quick_replies"
CONTENT_TYPE_FIELD = "content_type"

# received message fields
POSTBACK_FIELD = "postback"


class Recipient(Enum):
    PHONE_NUMBER = "phone_number"
    ID = "id"


class MessageType(Enum):
    TEXT = "text"
    ATTACHMENT = "attachment"


class AttachmentType(Enum):
    IMAGE = "image"
    TEMPLATE = "template"


class TemplateType(Enum):
    GENERIC = "generic"
    BUTTON = "button"
    RECEIPT = "receipt"


class ButtonType(Enum):
    WEB_URL = "web_url"
    POSTBACK = "postback"


class ContentType(Enum):
    TEXT = "text"
    LOCATION = "location"


class ActionButton:
    def __init__(self, button_type, title, url=None, payload=None):
        self.button_type = button_type
        self.title = title
        self.url = url
        self.payload = payload

    def to_dict(self):
        button_dict = dict()
        button_dict[TYPE_FIELD] = self.button_type.value
        if self.title:
            button_dict[TITLE_FIELD] = self.title
        if self.url is not None:
            button_dict[URL_FIELD] = self.url
        if self.payload is not None:
            button_dict[PAYLOAD_FIELD] = self.payload
        return button_dict


class GenericElement:
    def __init__(self, title, subtitle, image_url, buttons):
        self.title = title
        self.subtitle = subtitle
        self.image_url = image_url
        self.buttons = buttons

    def to_dict(self):
        element_dict = dict()
        if self.title:
            element_dict[TITLE_FIELD] = self.title
        if self.subtitle:
            element_dict[SUBTITLE_FIELD] = self.subtitle
        if self.image_url:
            element_dict[IMAGE_FIELD] = self.image_url
        buttons = list(dict())
        for i in range(len(self.buttons)):
            buttons.append(self.buttons[i].to_dict())
        element_dict[BUTTONS_FIELD] = buttons
        return element_dict


class QuickReply:
    def __init__(self, title, payload, image_url=None, content_type=ContentType.TEXT):
        self.title = title
        self.payload = payload
        self.image_url = image_url
        self.content_type = content_type

    def to_dict(self):
        reply_dict = dict()
        reply_dict[CONTENT_TYPE_FIELD] = self.content_type.value
        if self.title:
            reply_dict[TITLE_FIELD] = self.title
        reply_dict[PAYLOAD_FIELD] = self.payload
        if self.image_url is not None:
            reply_dict[IMAGE_FIELD] = self.image_url
        logger.debug('Reply dict: {}'.format(reply_dict))
        return reply_dict


class FacebookMessageType(Enum):
    received = "message"
    delivered = "delivery"
    read = "read"
    echo = "message"
    postback = "postback"


def recognize_message_type(message: Dict[str, Any]) -> FacebookMessageType:
    guess = None
    for key in FacebookMessageType:
        if message.get(key):
            guess = key

    if guess in (FacebookMessageType.received, FacebookMessageType.echo):
        guess = FacebookMessageType.echo if message['message'].get('is_echo', False) else FacebookMessageType.received

    return guess


class FacebookEntity:
    USER_FIELDS = ['first_name', 'last_name', 'profile_pic', 'locale',
                   'timezone', 'gender', 'is_payment_enabled', 'last_ad_referral']

    def __init__(self, user: Dict[str, Any]):
        self.id = user.get('id', None)

        # User data.
        self.first_name = None
        self.last_name = None
        self.profile_pic = None
        self.locale = None
        self.timezone = None
        self.gender = None
        self.is_payment_enabled = None
        self.last_ad_referral = None

    def hydrate_user_from_api(self, data: Dict[str, Any]):
        for key, value in data.items():
            setattr(self, key, value)  # Question to myself: json.loads should do the job and perform conversion, right?

    def __bool__(self):
        return self.id is not None


Coordinates = NamedTuple('Coordinates', [
    ('lat', float),
    ('long', float),
])


# FIXME: Add support for generic, list, open graph, receipt, airline stuff.
class FacebookTemplate:
    def __init__(self, template: Dict[str, Any]):
        self.type = template.get('template_type')
        self.buttons = [
            ActionButton(button.get('type'), title=button.get('title'), url=button.get('url'),
                         payload=button.get('payload'))
            for button in template.get('buttons', [])
        ]


class FacebookFallback:
    def __init__(self, fallback: Dict[str, Any]):
        self.title = fallback.get('title')
        self.url = fallback.get('url')
        self.payload = fallback.get('payload')


class FacebookAttachment:
    def __init__(self, attachment: Dict[str, Any]):
        self.type = attachment['type']
        if self.type in ('image', 'audio', 'video', 'file'):
            self.payload = attachment['payload']['url']
        elif self.type == 'location':
            self.payload = Coordinates(lat=float(attachment['payload']['lat']),
                                       long=float(attachment['payload']['long']))
        elif self.type == 'template':
            self.payload = FacebookTemplate(attachment['payload'])
        elif self.type == 'fallback':
            self.payload = FacebookFallback(attachment)


class FacebookReferralSource(Enum):
    m_me = 'SHORTLINK'
    ad_referral = 'ADS'
    parametric_messenger_code = 'MESSENGER_CODE'
    discover_tab = 'DISCOVER_TAB'


def recognize_referral_source(referral: Dict[str, Any]) -> FacebookReferralSource:
    return FacebookReferralSource(referral.get('source'))


class FacebookPostbackReferral:
    def __init__(self, referral: Optional[Dict[str, Any]]):
        if referral:
            self.referral_source = recognize_referral_source(referral)
        else:
            self.referral_source = None

    def __bool__(self):
        return self.referral_source is not None


class FacebookMessage:
    # Filled when the first instance is created.
    DISPATCHERS = {}
    initialized = False

    def __init__(self, message: Dict[str, Any]):
        if not self.__class__.initialized:
            self.__class__.DISPATCHERS = {
                FacebookMessageType.received: FacebookMessage._process_received,
                FacebookMessageType.delivered: FacebookMessage._process_delivered,
                FacebookMessageType.read: FacebookMessage._process_read,
                FacebookMessageType.echo: FacebookMessage._process_echo,
                FacebookMessageType.postback: FacebookMessage._process_postback,
            }
            self.__class__.initialized = True
            self.DISPATCHERS = self.__class__.DISPATCHERS

        self._message = message
        self.type = recognize_message_type(message)
        self.sender = FacebookEntity(message.get('sender'))
        self.recipient = FacebookEntity(message.get('recipient'))
        self.timestamp = message.get('timestamp')

        # Message / Received.
        self.mid = None
        self.text = None
        self.quick_reply_payload = None
        self.attachments = []

        # Echo
        self.metadata = None

        # Delivered
        self.mids = []
        self.watermark = None
        self.seq = None

        # Postback
        self.postback_payload = None
        self.referral = None

        self.DISPATCHERS[self.type](message)

    def _process_received(self):
        message = self._message['message']
        self.mid = message.get('mid')
        self.text = message.get('text')

        self.quick_reply_payload = message.get('quick_reply', {}).get('payload', None)
        for attachment in message.get('attachments', []):
            self.attachments.append(FacebookAttachment(attachment))

    def _process_delivered(self):
        message = self._message['delivery']

        self.mids.extend(message.get('mids', []))
        self.watermark = message['watermark']  # Always present per FB docs.
        self.seq = message.get('seq')

    def _process_read(self):
        message = self._message['read']

        self.watermark = message['watermark']
        self.seq = message.get('seqs')

    def _process_echo(self):
        message = self._message['message']

        self.app_id = message.get('app_id')
        self.metadata = message.get('metadata')
        self.mid = message.get('mid')
        self.text = message.get('text')

        for attachment in message.get('attachments', []):
            self.attachments.append(FacebookAttachment(attachment))

    def _process_postback(self):
        message = self._message['postback']

        self.postback_payload = message['payload']
        self.referral = FacebookPostbackReferral(message.get('referal'))


class FacebookEntry:
    def __init__(self, entry: Dict[str, Any]):
        self.id = entry['id']
        self.changed_fields = entry['changed_fields']
        self.changes = entry['changes']
        self.time = entry['timestamp']

        self.messages = self.process_messages(entry['messaging'])

    def process_messages(self, entries: List[Dict[str, Any]]) -> List[FacebookMessage]:
        messages = []
        for message in entries:
            messages.append(
                FacebookMessage(message)
            )
        return messages


class Messager:
    BASE_URL = "https://graph.facebook.com/v2.9/{}"

    def __init__(self, access_token):
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
        self.session.params = {
            'access_token': self.access_token
        }

    def subscribe_to_page(self):
        return self.session.post(self.BASE_URL.format("me/subscribed_apps"))

    def set_greeting_text(self, text):
        data = {"setting_type": "greeting", "greeting": {"text": text}}
        return self.session.post(self.BASE_URL.format("me/thread_settings"),
                                 data=json.dumps(data))

    def set_get_started_button_payload(self, payload):
        data = {"setting_type": "call_to_actions", "thread_state": "new_thread",
                "call_to_actions": [{"payload": payload}]}
        return self.session.post(self.BASE_URL.format("me/thread_settings"),
                                 data=json.dumps(data))

    def send_text(self, user_id, text):
        self._send({RECIPIENT_FIELD: self._build_recipient(user_id),
                    MESSAGE_FIELD: {MessageType.TEXT.value: text}})

    def send_image(self, user_id, image):
        self._send({RECIPIENT_FIELD: self._build_recipient(user_id),
                    MESSAGE_FIELD: {
                        ATTACHMENT_FIELD: {
                            TYPE_FIELD: AttachmentType.IMAGE.value,
                            PAYLOAD_FIELD: {
                                URL_FIELD: image
                            }
                        }
                    }})

    def send_buttons(self, user_id, title, button_list):
        buttons = list(dict())
        for i in range(len(button_list)):
            buttons.append(button_list[i].to_dict())

        self._send({RECIPIENT_FIELD: self._build_recipient(user_id),
                    MESSAGE_FIELD: {
                        ATTACHMENT_FIELD: {
                            TYPE_FIELD: AttachmentType.TEMPLATE.value,
                            PAYLOAD_FIELD: {
                                TEMPLATE_TYPE_FIELD: TemplateType.BUTTON.value,
                                TEXT_FIELD: title,
                                BUTTONS_FIELD: buttons
                            }
                        }
                    }})

    def send_generic(self, user_id, element_list):
        elements = list(dict())
        for i in range(len(element_list)):
            elements.append(element_list[i].to_dict())
        self._send({RECIPIENT_FIELD: self._build_recipient(user_id),
                    MESSAGE_FIELD: {
                        ATTACHMENT_FIELD: {
                            TYPE_FIELD: AttachmentType.TEMPLATE.value,
                            PAYLOAD_FIELD: {
                                TEMPLATE_TYPE_FIELD: TemplateType.GENERIC.value,
                                ELEMENTS_FIELD: elements
                            }
                        }
                    }})

    def send_quick_replies(self, user_id, title, reply_list):
        replies = list(dict())
        for r in reply_list:
            replies.append(r.to_dict())
        self._send({RECIPIENT_FIELD: self._build_recipient(user_id),
                    MESSAGE_FIELD: {
                        TEXT_FIELD: title,
                        QUICK_REPLIES_FIELD: replies
                    }})

    def typing(self, user_id, on=True):
        data = {RECIPIENT_FIELD: {"id": user_id}, "sender_action": "typing_on" if on else "typing_off"}
        return self.session.post(self.BASE_URL.format("me/messages"), data=json.dumps(data))

    def fetch_user(self, user_id, fields: List[str] = None) -> FacebookEntity:
        if fields is None:
            fields = FacebookEntity.USER_FIELDS

        entity = FacebookEntity(user_id)
        resp = self.session.get(
            self.BASE_URL
            .format('/{}'),
            params={
                'fields': ','.join(fields)
            }
        )

        resp.raise_for_status()

        entity.hydrate_user_from_api(resp.json())
        return entity

    @staticmethod
    def unserialize_received_request(object_type: str, json_entries: Dict[str, Any]) -> List[FacebookMessage]:
        if json_entries['object'] != object_type:
            raise RuntimeError('This message is not a page type')

        messages = []
        for entry in json_entries['entry']:
            fb_entry = FacebookEntry(entry)
            messages.extend(fb_entry.messages)

        return messages

    @staticmethod
    def _build_recipient(user_id):
        return {Recipient.ID.value: user_id}

    def _send(self, message_data):
        post_message_url = self.BASE_URL.format("me/messages")
        response_message = json.dumps(message_data)
        logger.debug('Message: {}'.format(response_message))
        req = self.session.post(post_message_url,
                                data=response_message)
        logger.info("[{status}/{reason}/{text}] Reply to {recipient}: {content}".format(
            status=req.status_code,
            reason=req.reason,
            text=req.text,
            recipient=message_data[RECIPIENT_FIELD],
            content=message_data[MESSAGE_FIELD]))
