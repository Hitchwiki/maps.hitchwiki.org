import os
import secrets

from flask import Flask, redirect, request, session, url_for
from requests_oauthlib import OAuth1Session

app = Flask(__name__)
app.secret_key = os.getenv("OAUTH_SECRET_KEY", secrets.token_hex(32))

# OAuth credentials from MediaWiki
CONSUMER_KEY = os.getenv("OAUTH_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("OAUTH_CONSUMER_SECRET")

# Validate required environment variables
if not CONSUMER_KEY or not CONSUMER_SECRET:
    raise ValueError("OAUTH_CONSUMER_KEY and OAUTH_CONSUMER_SECRET environment variables must be set")

# MediaWiki OAuth endpoints
MEDIAWIKI_BASE_URL = 'https://nomadwiki.org'
REQUEST_TOKEN_URL = f'{MEDIAWIKI_BASE_URL}/w/index.php?title=Special:OAuth/initiate'
AUTHORIZATION_URL = f'{MEDIAWIKI_BASE_URL}/w/index.php?title=Special:OAuth/authorize'
ACCESS_TOKEN_URL = f'{MEDIAWIKI_BASE_URL}/w/index.php?title=Special:OAuth/token'

@app.route('/login')
def login():
    # Step 1: Get request token
    oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri=url_for('callback', _external=True))
    request_token = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    
    # Store request token in session
    session['oauth_token'] = request_token['oauth_token']
    session['oauth_token_secret'] = request_token['oauth_token_secret']
    
    # Step 2: Redirect user to authorization URL
    authorization_url = oauth.authorization_url(AUTHORIZATION_URL)
    return redirect(authorization_url)

@app.route('/oauth/callback')
def callback():
    # Step 3: Handle callback and get access token
    oauth_token = session.get('oauth_token')
    oauth_token_secret = session.get('oauth_token_secret')
    oauth_verifier = request.args.get('oauth_verifier')
    
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
        verifier=oauth_verifier
    )
    
    access_token = oauth.fetch_access_token(ACCESS_TOKEN_URL)
    
    # Store access token in session
    session['access_token'] = access_token['oauth_token']
    session['access_token_secret'] = access_token['oauth_token_secret']
    
    # Step 4: Get user info
    user_info = get_user_info(access_token['oauth_token'], access_token['oauth_token_secret'])
    
    # Store user info in session or database
    session['user'] = user_info
    
    return redirect(url_for('dashboard'))

def get_user_info(access_token, access_token_secret):
    """Fetch user information from MediaWiki API"""
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret
    )
    
    # Get user info using MediaWiki API
    response = oauth.get(f'{MEDIAWIKI_BASE_URL}/w/api.php?action=query&meta=userinfo&uiprop=groups|rights|editcount&format=json')
    
    if response.status_code == 200:
        data = response.json()
        return data['query']['userinfo']
    return None

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = session['user']
    return f"Welcome, {user['name']}! You have {user['editcount']} edits."

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':

    # Run the app
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        host='0.0.0.0',
        port=int(os.getenv('PORT', 4242))
    )