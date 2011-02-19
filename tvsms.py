#!/usr/bin/env python
#
# Copyright 2009 FriendFeed
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""A Python implementation of the FriendFeed API v2

Documentation is available at http://friendfeed.com/api/documentation.
For a complete example application using this library, see
http://code.google.com/p/friendfeed-api-example/.

For version 1 of the API, see
http://code.google.com/p/friendfeed-api/wiki/ApiDocumentation.
"""

import binascii
import cgi
import datetime
import functools
import hashlib
import hmac
import time
import urllib
import urllib2
import urlparse
import uuid

# Find a JSON parser
try:
    import simplejson
    _parse_json = lambda s: simplejson.loads(s.decode("utf-8"))
except ImportError:
    try:
        import cjson
        _parse_json = lambda s: cjson.decode(s.decode("utf-8"), True)
    except ImportError:
        try:
            import json
            _parse_json = lambda s: _unicodify(json.read(s))
        except ImportError:
            # For Google AppEngine
            from django.utils import simplejson
            _parse_json = lambda s: simplejson.loads(s.decode("utf-8"))

_FRIENDFEED_API_BASE = "http://friendfeed-api.com/v2"
_FRIENDFEED_OAUTH_BASE = "https://friendfeed.com/account/oauth"


def _authenticated(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.consumer_token or not self.access_token:
            raise Exception("OAuth required for this method")
        return method(self, *args, **kwargs)
    return wrapper


class FriendFeed(object):
    def __init__(self, oauth_consumer_token=None, oauth_access_token=None):
        """Initializes a FriendFeed session.

        To make authenticated requests to FriendFeed, which is required for
        some feeds and to post messages, you must provide both
        oauth_consumer_token and oauth_access_token. They should both be
        dictionaries of the form {"key": "...", "secret": "..."}. Learn
        more about OAuth at http://friendfeed.com/api/documentation#oauth.

        You can register your application to receive your FriendFeed OAuth
        Consumer Key at http://friendfeed.com/api/register. To fetch request
        tokens and access tokens, see fetch_oauth_request_token and
        fetch_oauth_access_token below.
        """
        self.consumer_token = oauth_consumer_token
        self.access_token = oauth_access_token

    def set_oauth(self, consumer_token, access_token):
        """Sets the OAuth parameters for this session."""
        self.consumer_token = consumer_token
        self.access_token = access_token

    
    @_authenticated
    def post_entry(self, body, link=None, to=None, **args):
        """Posts the given message to FriendFeed (link and to optional).

        See http://friendfeed.com/api/documentation#write_entry.
        Authentication is required for this method.
        """
        args.update(body=body)
        if link: args.update(link=link)
        if to: args.update(to=to)
        return self.fetch("/entry", post_args=args)

    
    def fetch(self, path, post_args=None, **args):
        """Fetches the given relative API path, e.g., "/bret/friends"

        If the request is a POST, post_args should be provided. Query
        string arguments should be given as keyword arguments.
        """
        url = _FRIENDFEED_API_BASE + path

        # Add the OAuth resource request signature if we have credentials
        if self.consumer_token and self.access_token:
            all_args = {}
            all_args.update(args)
            all_args.update(post_args or {})
            oauth = get_oauth_resource_request_parameters(
                url, self.consumer_token, self.access_token, all_args,
                method="POST" if post_args is not None else "GET")
            args.update(oauth)

        if args: url += "?" + urllib.urlencode(args)
        if post_args is not None:
            request = urllib2.Request(url, urllib.urlencode(post_args))
        else:
            request = urllib2.Request(url)
        stream = urllib2.urlopen(request)
        data = stream.read()
        stream.close()
        return self._parse_dates(_parse_json(data))

    def _parse_dates(self, obj):
        if isinstance(obj, dict):
            for name in obj.keys():
                if name == u"date":
                    obj[name] = datetime.datetime.strptime(
                        obj[name], "%Y-%m-%dT%H:%M:%SZ")
                else:
                    self._parse_dates(obj[name])
        elif isinstance(obj, list):
            for subobj in obj:
                self._parse_dates(subobj)
        return obj


def get_oauth_request_token_url(consumer_token):
    """Returns the Unauthorized Request Token URL for FriendFeed.

    See http://oauth.net/core/1.0/#auth_step1
    """
    url = _FRIENDFEED_OAUTH_BASE + "/request_token"
    args = dict(
        oauth_consumer_key=consumer_token["key"],
        oauth_signature_method="HMAC-SHA1",
        oauth_timestamp=str(int(time.time())),
        oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
        oauth_version="1.0",
    )
    signature = _oauth_signature(consumer_token, "GET", url, args)
    args["oauth_signature"] = signature
    return url + "?" + urllib.urlencode(args)


def get_oauth_authorization_url(request_token):
    """Returns the FriendFeed authorization URL for the given request token.

    The user should be directed to this URL to authorize a request token.
    After the user authorizes a token, the user will be redirected to the
    callback URL you specified when you registered your FriendFeed API
    application at http://friendfeed.com/api/register. FriendFeed does
    not support the oauth_callback argument.

    See http://oauth.net/core/1.0/#auth_step2
    """
    return _FRIENDFEED_OAUTH_BASE + "/authorize?" + \
        urllib.urlencode(dict(oauth_token=request_token["key"]))


def get_oauth_authentication_url(request_token):
    """Returns the FriendFeed authentication URL for the given request token.

    The user should be directed to this URL to authorize a request token.
    After the user authorizes a token, the user will be redirected to the
    callback URL you specified when you registered your FriendFeed API
    application at http://friendfeed.com/api/register. FriendFeed does
    not support the oauth_callback argument.

    See http://oauth.net/core/1.0/#auth_step2
    """
    return _FRIENDFEED_OAUTH_BASE + "/authenticate?" + \
        urllib.urlencode(dict(oauth_token=request_token["key"]))


def get_oauth_access_token_url(consumer_token, request_token):
    """Returns the Access Token URL for the given authorized request token.

    The given request token must have been authorized by sending the user
    to the URL returned by get_oauth_authorization_url() before this URL
    is fetched.

    See http://oauth.net/core/1.0/#auth_step3
    """
    url = _FRIENDFEED_OAUTH_BASE + "/access_token"
    args = dict(
        oauth_consumer_key=consumer_token["key"],
        oauth_token=request_token["key"],
        oauth_signature_method="HMAC-SHA1",
        oauth_timestamp=str(int(time.time())),
        oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
        oauth_version="1.0",
    )
    signature = _oauth_signature(consumer_token, "GET", url, args,
                                request_token)
    args["oauth_signature"] = signature
    return url + "?" + urllib.urlencode(args)


def get_installed_app_access_token_url(consumer_token, username, password):
    """Returns the installed application Access Token URL for the 
    given username and password.

    See http://friendfeed.com/api/documentation#authentication
    """
    url = _FRIENDFEED_OAUTH_BASE + "/ia_access_token"
    args = dict(
        oauth_consumer_key=consumer_token["key"],
        ff_username=username,
        ff_password=password,
        oauth_signature_method="HMAC-SHA1",
        oauth_timestamp=str(int(time.time())),
        oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
        oauth_version="1.0",
    )
    signature = _oauth_signature(consumer_token, "GET", url, args)
    args["oauth_signature"] = signature
    return url + "?" + urllib.urlencode(args)


def get_oauth_resource_request_parameters(url, consumer_token, access_token,
                                          parameters={}, method="GET"):
    """Returns the OAuth parameters as a dict for the given resource request.

    parameters should include all POST arguments and query string arguments
    that will be sent with the request.
    """
    base_args = dict(
        oauth_consumer_key=consumer_token["key"],
        oauth_token=access_token["key"],
        oauth_signature_method="HMAC-SHA1",
        oauth_timestamp=str(int(time.time())),
        oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
        oauth_version="1.0",
    )
    args = {}
    args.update(base_args)
    args.update(parameters)
    signature = _oauth_signature(consumer_token, method, url, args,
                                access_token)
    base_args["oauth_signature"] = signature
    return base_args


def fetch_oauth_request_token(consumer_token):
    """Fetches a new, unauthorized request token from FriendFeed.

    See get_oauth_request_token_url().
    """
    url = get_oauth_request_token_url(consumer_token)
    request = urllib2.urlopen(url)
    token = _oauth_parse_response(request.read())
    request.close()
    return token


def fetch_oauth_access_token(consumer_token, request_token):
    """Fetches an access token for the given authorized request token.

    See get_oauth_access_token_url().
    """
    url = get_oauth_access_token_url(consumer_token, request_token)
    request = urllib2.urlopen(url)
    token = _oauth_parse_response(request.read())
    request.close()
    return token


def fetch_installed_app_access_token(consumer_token, username, password):
    """Fetches an access token for the given username and password.

    See get_installed_app_access_token_url().
    """
    url = get_installed_app_access_token_url(consumer_token, username, password)
    request = urllib2.urlopen(url)
    token = _oauth_parse_response(request.read())
    request.close()
    return token


def _oauth_signature(consumer_token, method, url, parameters={}, token=None):
    """Calculates the HMAC-SHA1 OAuth signature for the given request.

    See http://oauth.net/core/1.0/#signing_process
    """
    parts = urlparse.urlparse(url)
    scheme, netloc, path = parts[:3]
    normalized_url = scheme.lower() + "://" + netloc.lower() + path

    base_elems = []
    base_elems.append(method.upper())
    base_elems.append(normalized_url)
    base_elems.append("&".join("%s=%s" % (k, _oauth_escape(str(v)))
                               for k, v in sorted(parameters.items())))
    base_string =  "&".join(_oauth_escape(e) for e in base_elems)

    key_elems = [consumer_token["secret"]]
    key_elems.append(token["secret"] if token else "")
    key = "&".join(key_elems)

    hash = hmac.new(key, base_string, hashlib.sha1)
    return binascii.b2a_base64(hash.digest())[:-1]


def _oauth_escape(val):
    if isinstance(val, unicode):
        val = val.encode("utf-8")
    return urllib.quote(val, safe="~")


def _oauth_parse_response(body):
    p = cgi.parse_qs(body, keep_blank_values=False)
    token = dict(key=p["oauth_token"][0], secret=p["oauth_token_secret"][0])

    # Add the extra parameters the Provider included to the token
    special = ("oauth_token", "oauth_token_secret")
    token.update((k, p[k][0]) for k in p if k not in special)
    return token
