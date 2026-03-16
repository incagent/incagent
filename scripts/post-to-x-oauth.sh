#!/bin/bash

# Post to X (@incagentai) using OAuth 1.0
# Requires: write:tweets permission enabled in X Developer Portal

CONSUMER_KEY="SQ6SxbTXiurLARHYz6MZ7rFWF"
CONSUMER_SECRET="EHwGyHtrlajsuXCKRzeBR81gFE6CRokVSrjoQJ9mrCoufGygti"
ACCESS_TOKEN="2008667478570975232-gNoRtyUlcFJTzzqRhywszsePbJRqWb"
ACCESS_TOKEN_SECRET="tPTXHsZjJUWMTKIBg4rPBgMeQl35CNoN4kgVt0BRsdh9s"

TWEET="$1"
if [ -z "$TWEET" ]; then
  echo "Usage: post-to-x-oauth.sh \"Your tweet text\""
  exit 1
fi

python3 << PYTHON
import hmac, hashlib, time, random, string, urllib.parse, urllib.request, json, base64

consumer_key = "$CONSUMER_KEY"
consumer_secret = "$CONSUMER_SECRET"
access_token = "$ACCESS_TOKEN"
access_token_secret = "$ACCESS_TOKEN_SECRET"

url = "https://api.twitter.com/1.1/statuses/update.json"
tweet_text = """$TWEET"""

nonce = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
timestamp = str(int(time.time()))

oauth_params = {
    "oauth_consumer_key": consumer_key,
    "oauth_nonce": nonce,
    "oauth_signature_method": "HMAC-SHA1",
    "oauth_timestamp": timestamp,
    "oauth_token": access_token,
    "oauth_version": "1.0",
    "status": tweet_text
}

def pct(s):
    return urllib.parse.quote(str(s), safe='')

param_str = "&".join(f"{pct(k)}={pct(v)}" for k, v in sorted(oauth_params.items()))
base_str = f"POST&{pct(url)}&{pct(param_str)}"
signing_key = f"{pct(consumer_secret)}&{pct(access_token_secret)}"
sig = base64.b64encode(hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()

oauth_header_params = {k: v for k, v in oauth_params.items() if k.startswith('oauth')}
oauth_header_params["oauth_signature"] = sig
auth_header = "OAuth " + ", ".join(f'{pct(k)}="{pct(v)}"' for k, v in sorted(oauth_header_params.items()))

body = urllib.parse.urlencode({"status": tweet_text}).encode()
req = urllib.request.Request(url, data=body, headers={"Authorization": auth_header}, method="POST")

try:
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read().decode())
        print(f"✓ POSTED: https://twitter.com/incagentai/status/{resp['id_str']}")
except urllib.error.HTTPError as e:
    print(f"✗ Failed: {e.code}")
    print(e.read().decode())
PYTHON
