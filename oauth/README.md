# Hitchwiki OAuth2 Login

Users log in to the Hitchhiking Map via their Hitchwiki account using OAuth2. On first login, a local user account is auto-created using the Hitchwiki username and email.

## OAuth Consumer Configuration

The OAuth consumer must be created at https://hitchwiki.org/en/Special:OAuthConsumerRegistration/propose with these settings:

| Setting | Value |
|---------|-------|
| Application name | maps.hitchwiki.org Login |
| Consumer version | 1.0 |
| OAuth protocol version | **OAuth 2.0** |
| Owner-only | No |
| Applicable project | All projects |
| OAuth "callback URL" | `https://maps.hitchwiki.org/login` |
| Allow consumer to specify a callback in requests | No |
| Applicable grants | **User identity verification only with access to real name and email address**, no ability to read pages or act on a user's behalf |
| Client is confidential | Yes |

After creation you receive a **client ID** and **client secret**. Add them to your `.env`:

```
HITCHWIKI_OAUTH_CLIENT_ID = <client_id>
HITCHWIKI_OAUTH_CLIENT_SECRET = <client_secret>
```

## OAuth2 Endpoints Used

- Authorize: `https://hitchwiki.org/en/rest.php/oauth2/authorize`
- Token: `https://hitchwiki.org/en/rest.php/oauth2/access_token`
- Profile: `https://hitchwiki.org/en/rest.php/oauth2/resource/profile`

## Test Script

`test_hitchwiki_oauth2.py` is a standalone Flask app for testing the OAuth2 flow independently:

```
pip install flask requests
OAUTHLIB_INSECURE_TRANSPORT=1 python oauth/test_hitchwiki_oauth2.py
```

Visit http://127.0.0.1:5001/login to test.

## Cloudflare Notes

If the wiki is behind Cloudflare, the OAuth endpoints may be blocked by Cloudflare's bot protection. To fix this, add a Cloudflare Configuration Rule:

1. Go to **Rules > Configuration Rules** in the Cloudflare dashboard
2. Create a rule named "Bypass OAuth endpoint"
3. Expression: `(http.request.uri.path contains "/w/index.php" and http.request.uri.query contains "title=Special:OAuth")`
4. Settings: Security Level → Essentially Off, Cache Level → Bypass, Disable Browser Integrity Check (optional)
5. Save and deploy
