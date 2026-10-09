# Security

## Reporting a problem

Please email security reports to the address set as `CONTACT_EMAIL` for the
deployment you use (runnify.dev@gmail.com for the main one), with steps to
reproduce. Don't open a public issue for a vulnerability, and don't access
other people's data while testing.

## How accounts are protected

- **Passwords** are hashed with Argon2id and upgraded transparently when the
  parameters change. The policy follows NIST SP 800-63B: 12 to 128 characters,
  no composition rules, and common, repetitive or personal passwords (including
  padded and leetspeak variants) are refused.
- **Sign-in** is rate limited per address, and after repeated failures an
  account pauses for a while (doubling with each further failure, up to a day)
  and the owner is emailed. Failure messages never reveal whether an account
  exists.
- **Two-step verification** with an authenticator app is optional; ten
  single-use recovery codes are stored only as hashes, and each code works once.
- **Sessions** carry a per-account token, so changing the password, resetting it
  or choosing "sign out everywhere else" ends every other session at once.
- **Password resets** use single-use links that expire after 30 minutes and stop
  working once the password changes. The token is moved out of the URL as soon
  as the link is opened.
- **Sensitive actions** (changing the name or password, two-step changes,
  downloading or deleting data) ask for the current password again.
- **An activity log** in Settings shows sign-ins and account changes with the
  device and network, kept for 90 days.

## How data is protected

- Garmin and Spotify tokens are encrypted at rest with Fernet, with key rotation.
  The Garmin password is used once to sign in and never stored.
- Uploaded Spotify history zips are checked for size and compression before
  they are read, only plays during runs are kept, and the file is deleted after
  import.
- Users can download everything held about them as JSON, or delete their
  account and all of its data, from Settings.

## How the site is protected

- CSRF tokens on every form; state changes only happen on POST.
- A strict Content-Security-Policy: scripts, styles, fonts and images only from
  the site itself, no inline code, no framing. No third-party scripts, fonts,
  analytics or trackers are loaded.
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy` and
  `Cross-Origin-Resource-Policy` on every response; HSTS over HTTPS in
  production; personal pages are sent with `Cache-Control: no-store`.
- Secure, HttpOnly, SameSite cookies in production; only the session and the
  optional remember-me cookie are set.
- Host headers are checked against `ALLOWED_HOSTS`, emailed links use the
  configured public origin, and redirects after sign-in only go to local paths.
- Production refuses to start without a strong `SECRET_KEY`, a valid
  `FERNET_KEY`, an `https://` public origin and allowed hosts.
