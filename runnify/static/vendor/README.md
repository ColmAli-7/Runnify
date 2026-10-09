# Vendored third-party assets

Runnify serves every script and font itself, so pages make no third-party
requests and the Content-Security-Policy can allow `'self'` only. Each file
below is an unmodified copy of the published release.

| File | Version | Source | SHA-256 | Licence |
|---|---|---|---|---|
| `vendor/gsap/gsap.min.js` | GSAP 3.15.0 | https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js | `92bb9a96476f983d212a2bc4f54c889039c1696dd4461d40a736860938570fbb` | GSAP Standard "No Charge" License, https://gsap.com/standard-license |
| `vendor/gsap/ScrollTrigger.min.js` | GSAP 3.15.0 | https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/ScrollTrigger.min.js | `b0b14d67b55b0c43c756ac0b106cfcb09d0879945f6ead64451065b0672916a2` | GSAP Standard "No Charge" License |
| `fonts/geist/Geist-Variable.woff2` | Geist 1.7.2 | https://cdn.jsdelivr.net/npm/geist@1.7.2/dist/fonts/geist-sans/Geist-Variable.woff2 | `a369fcf5628ea2aa4e1b9e2ec6a5b3624e365bda588e1f0f2f12b564f728fbb8` | SIL Open Font License 1.1 (`fonts/geist/OFL.txt`) |

To update a file, download the new release, replace it, and update its row
(`sha256sum <file>`).
