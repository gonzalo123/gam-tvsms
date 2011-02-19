#!/usr/bin/env python

# To get a FriendFeed API Consumer Token for your application,
# visit http://friendfeed.com/api/register
FRIENDFEED_API_TOKEN = dict(
    key="--",
    secret="--",
)

import base64
import binascii
import Cookie
import email.utils
import friendfeed
import functools
import hashlib
import hmac
import logging
import os
import time
import urllib2
import traceback, cStringIO

from django.utils import simplejson
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

def authenticated(method):
    """Decorator that requires the user is logged into FriendFeed via OAuth.

    The authenticated FriendFeed session becomes available as self.friendfeed
    when this decorator is used. The username of the authenticated user is
    available as self.friendfeed_username.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        cookie_val = parse_cookie(self.request.cookies.get("FF_API_AUTH"))
        if not cookie_val:
            if self.request.method != "GET":
                #self.error(403)
                self.response.headers['Content-Type'] = 'application/json'
                jsonData = {"redirect" : '/oauth/authorize'}
                self.response.out.write(simplejson.dumps(jsonData))
                return
            #self.redirect("/oauth/authorize")
            self.response.headers['Content-Type'] = 'application/json'
            jsonData = {"redirect" : '/oauth/authorize'}
            self.response.out.write(simplejson.dumps(jsonData))
        try:
            key, secret, username = cookie_val.split("|")
        except:
            self.response.headers['Content-Type'] = 'application/json'
            jsonData = {"redirect" : '/oauth/authorize'}
            self.response.out.write(simplejson.dumps(jsonData))
            return
        self.friendfeed = friendfeed.FriendFeed(
            FRIENDFEED_API_TOKEN, dict(key=key, secret=secret))
        self.friendfeed_username = username
        return method(self, *args, **kwargs)
    return wrapper

class OAuthCheck(webapp.RequestHandler):
    @authenticated
    def post(self):
        cookie_val = parse_cookie(self.request.cookies.get("FF_API_AUTH"))
        try:
            key, secret, username = cookie_val.split("|")
            self.response.headers['Content-Type'] = 'application/json'
            jsonData = {"ok" : 1}
            self.response.out.write(simplejson.dumps(jsonData))
        except:
            self.response.headers['Content-Type'] = 'application/json'
            jsonData = {"redirect" : '/oauth/authorize'}
            self.response.out.write(simplejson.dumps(jsonData))
        return


class EntryHandler(webapp.RequestHandler):
    @authenticated
    def post(self):
        try:
            entry = self.friendfeed.post_entry(
                body=self.request.get("body"),
                to=self.request.get("to"))
            out = {'error' : 0}
        except:
            out = {"redirect" : '/oauth/authorize'}
        self.response.headers['Content-Type'] = 'application/json'
        jsonData = out
        self.response.out.write(simplejson.dumps(jsonData))
        return

class OAuthCallbackHandler(webapp.RequestHandler):
    """Saves the FriendFeed OAuth user data in the FF_API_AUTH cookie."""
    def get(self):
        request_key = self.request.get("oauth_token")
        cookie_val = parse_cookie(self.request.cookies.get("FF_API_REQ"))
        if not cookie_val:
            logging.warning("Missing request token cookie")
            self.redirect("/")
            return
        cookie_key, cookie_secret = cookie_val.split("|")
        if cookie_key != request_key:
            logging.warning("Request token does not match cookie")
            self.redirect("/")
            return
        req_token = dict(key=cookie_key, secret=cookie_secret)
        try:
            access_token = friendfeed.fetch_oauth_access_token(
                FRIENDFEED_API_TOKEN, req_token)
        except:
            logging.warning("Could not fetch access token for %r", request_key)
            self.redirect("/")
            return
        data = "|".join(access_token[k] for k in ["key", "secret", "username"])
        set_cookie(self.response, "FF_API_AUTH", data,
                   expires=time.time() + 30 * 86400)
        self.redirect("/")


class OAuthAuthorizeHandler(webapp.RequestHandler):
    """Redirects the user to authenticate with FriendFeed."""
    def get(self):
        # Save the Request Token in a cookie to verify upon callback to help
        # prevent http://oauth.net/advisories/2009-1
        token = friendfeed.fetch_oauth_request_token(FRIENDFEED_API_TOKEN)
        data = "|".join([token["key"], token["secret"]])
        set_cookie(self.response, "FF_API_REQ", data)
        self.redirect(friendfeed.get_oauth_authentication_url(token))


def set_cookie(response, name, value, domain=None, path="/", expires=None):
    """Generates and signs a cookie for the give name/value"""
    timestamp = str(int(time.time()))
    value = base64.b64encode(value)
    signature = cookie_signature(value, timestamp)
    cookie = Cookie.BaseCookie()
    cookie[name] = "|".join([value, timestamp, signature])
    cookie[name]["path"] = path
    if domain: cookie[name]["domain"] = domain
    if expires:
        cookie[name]["expires"] = email.utils.formatdate(
            expires, localtime=False, usegmt=True)
    response.headers._headers.append(("Set-Cookie", cookie.output()[12:]))


def parse_cookie(value):
    """Parses and verifies a cookie value from set_cookie"""
    if not value: return None
    parts = value.split("|")
    if len(parts) != 3: return None
    if cookie_signature(parts[0], parts[1]) != parts[2]:
        logging.warning("Invalid cookie signature %r", value)
        return None
    timestamp = int(parts[1])
    if timestamp < time.time() - 30 * 86400:
        logging.warning("Expired cookie %r", value)
        return None
    try:
        return base64.b64decode(parts[0]).strip()
    except:
        return None


def cookie_signature(*parts):
    """Generates a cookie signature.

    We use the FriendFeed API token since it is different for every app (so
    people using this example don't accidentally all use the same secret).
    """
    hash = hmac.new(FRIENDFEED_API_TOKEN["secret"], digestmod=hashlib.sha1)
    for part in parts: hash.update(part)
    return hash.hexdigest()


application = webapp.WSGIApplication([
    (r"/oauth/callback", OAuthCallbackHandler),
    (r"/oauth/authorize", OAuthAuthorizeHandler),
    (r"/oauth/check", OAuthCheck),
    (r"/a/entry", EntryHandler),
])

def main():
    import google.appengine.ext.webapp.util
    google.appengine.ext.webapp.util.run_wsgi_app(application)


if __name__ == "__main__":
  main()
