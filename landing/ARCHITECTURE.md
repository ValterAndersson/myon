# Landing Page Architecture

Marketing landing page for Povver at [povver.ai](https://povver.ai). Static site with zero external dependencies and no build step.

## Hosting

EC2 instance (Amazon Linux 2023) in eu-west-1 with nginx. Let's Encrypt SSL via certbot with automatic renewal.

- **Instance**: `ec2-34-244-201-109.eu-west-1.compute.amazonaws.com`
- **Domain**: `povver.ai` (Route53 A record pointing to the instance IP)
- **SSH user**: `ec2-user`
- **Web root**: `/usr/share/nginx/html/`
- **SSL cert**: `/etc/letsencrypt/live/povver.ai/` (auto-renews via certbot timer)

## File Structure

```
landing/
├── ARCHITECTURE.md          # This file
├── index.html               # Single-page landing (SEO meta, OG, JSON-LD, cookie banner)
├── privacy.html             # Privacy Policy — litigation-hardened, multi-jurisdiction
├── tos.html                 # Terms of Service — 23 sections, arbitration, class action waiver
├── styles.css               # All styles — mobile-first, CSS custom properties, cookie banner
├── legal.css                # Shared styles for legal pages (privacy, tos)
├── script.js                # Scroll animations, mobile nav, cookie consent, GA4 event tracking
├── deploy.sh                # SCP deploy to EC2 instance
├── robots.txt               # Disallow all (staging — remove for launch)
└── assets/
    ├── favicon.svg           # SVG favicon (emerald "P")
    ├── statusbar.svg         # iOS status bar overlay (unused — real screenshots have it)
    └── screenshots/          # App screenshots (iPhone, 520px wide for 2x Retina)
        ├── coach.png         # Hero: Coach tab home screen
        ├── recommendations.png # Feature 1: Activity feed with Auto-Pilot
        ├── plan.png          # Feature 2: AI-generated workout plan
        ├── grid.png          # Feature 3: Set logging grid
        ├── train.png         # Feature 4: Train tab
        └── workout.png       # Currently unused (keyboard-open grid)
```

## Design Decisions

**Mobile-first CSS**: Base styles target mobile (375px). Desktop layout scales up via `@media (min-width: 768px)`. Design tokens in `:root` use mobile values; the `min-width` media query overrides them for desktop (nav height, section padding, container padding).

**Brand tokens**: Accent green `#22C59A`, dark background `#0A0E14`, Inter font via Google Fonts with system fallback. Full token set in `:root` CSS custom properties.

**Phone mockups**: On desktop, screenshots render inside a dark device frame (42px border-radius, 6px padding, 280px wide) with a floating bob animation and radial glow. On mobile, device frames are 220px with a smaller glow, no float animation.

**Hero on mobile**: Phone mockup is hidden to avoid back-to-back phones with the first feature screenshot. Text-only hero with centered layout: label pill, headline, subtitle, App Store button, scroll cue.

**Feature numbering**: Each feature section has an `01`–`04` accent-colored number label above the title for visual progression.

**Staggered scroll animations**: Feature screenshots animate in first via IntersectionObserver; text content follows with a 150ms delay. Highlight stats cascade in sequentially with 100ms offsets.

**Scroll cue**: A pulsing green dot with a gradient line at the bottom of the hero. Fades out via JS after 80px of scroll.

**Grain texture**: A subtle SVG noise overlay (`opacity: 0.02`) fixed over the entire viewport for tactile depth.

**No build step**: The page is three files (HTML, CSS, JS) deployed directly. Cache busting via `?v=N` query string on the CSS link.

**Cookie consent**: GA4 (`G-V9YHQNJTB7`) is loaded only after user consent. The banner appears after 1.5s on first visit, stores preference in `localStorage` as `povver_cookie_consent`. GA4 script is injected dynamically on acceptance — never loaded if declined or before consent. Compliant with EU ePrivacy Directive (opt-in required for analytics cookies per CJEU Planet49 ruling).

**GA4 event tracking**: Custom events sent via `gtag()` through a `track()` helper that no-ops before GA4 loads. Events: `landing_page_viewed` (with `referrer`, `utm_source`, `utm_medium`, `utm_campaign`), `app_store_click` (with `link_location`: hero/cta_footer/nav, `link_url`), `cookie_consent_accepted`, `section_view` (with `section_name` and `section_index`, fires once per section at 30% visibility). Cookie decline count tracked via `localStorage` only (GA4 not loaded). Same GA4 property as the iOS app (property 488064435) for cross-platform funnel tracking.

**App Store attribution**: Store buttons carry campaign tokens (`ct=landing_hero`, `ct=landing_cta_footer`) for App Store Connect analytics. Apple ID: `6759248585`. Smart App Banner meta tag included for Safari native install prompts.

**Legal pages**: Privacy Policy and Terms of Service are litigation-hardened for multi-jurisdiction compliance. Key protections: explicit health data consent, AI wiretap/transmission disclosure, mandatory pre-suit notice period, 1-year limitation period, ICC arbitration for non-EU users, class action and jury trial waivers, prevailing party fee-shifting, California auto-renewal compliance, EU right of withdrawal, BIPA-safe (explicit no-biometric-data statement). Age minimum is 18+.

## Page Sections

1. **Nav** — Fixed, transparent over dark hero, glassmorphic (`backdrop-filter: blur(20px)`) when scrolled past hero
2. **Hero** — Mesh gradient background (multiple radial gradients), animated gradient accent text, phone mockup (desktop only), scroll cue
3. **Features** (x4) — Alternating left/right layout on desktop. On mobile, screenshots shown first (`order: -1`), then text. Numbered 01–04. Gradient dividers between sections, alternating subtle backgrounds
4. **Highlights** — 3-column stat grid (900+, Every, Free) with gradient text values and vertical dividers
5. **Final CTA** — Centered radial glow, accent gradient divider at top
6. **Cookie banner** — Fixed bottom bar, glassmorphic, Accept/Decline buttons, slides up after 1.5s
7. **Footer** — Dark, minimal

## Deployment

### Quick deploy

```bash
cd landing
./deploy.sh
```

No env vars needed — the script auto-finds the PEM key.

### How it works

The deploy script SCPs all site files and assets to the EC2 instance, then copies them into the nginx web root with `sudo`. It also stamps cache-busting `?v=<timestamp>` query strings onto all `.png`, `.css`, and `.js` references in `index.html` (working on a temp copy — source files stay clean).

**PEM key resolution** (first match wins):

| Priority | Location | When to use |
|----------|----------|-------------|
| 1 | `$POVVER_PEM` | Env var override for non-standard setups |
| 2 | `landing/povver-rsa.pem` | Default — co-located with deploy script |
| 3 | `~/.ssh/povver-rsa.pem` | Alternative if you prefer keys in `~/.ssh/` |

The PEM file is gitignored (`*.pem` in root `.gitignore`). It must have `chmod 400` permissions.

### EC2 instance

| Property | Value |
|----------|-------|
| Host | `ec2-34-244-201-109.eu-west-1.compute.amazonaws.com` |
| Domain | `povver.ai` (Route53 A record) |
| SSH user | `ec2-user` |
| Web root | `/usr/share/nginx/html/` |
| SSL | Let's Encrypt via certbot (auto-renews) |
| OS | Amazon Linux 2023 |
| Region | eu-west-1 |

### Caching

Nginx is configured with cache headers in `/etc/nginx/default.d/cache.conf` (inside the server block):

- **HTML**: `no-cache, must-revalidate` — browser always revalidates, so new deploys are picked up immediately.
- **Assets** (`.png`, `.css`, `.js`, `.svg`, `.woff2`): `public, max-age=31536000, immutable` — cached for 1 year. The deploy script adds `?v=<timestamp>` to all asset references in `index.html`, so updated assets get a new URL and bypass the cache.

This means: deploy the script, and changes are live immediately. No manual cache clearing needed.

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PEM key not found` | Key missing from all 3 locations | Get `povver-rsa.pem` from team and place in `landing/` |
| `Permission denied (publickey)` | Wrong PEM file or bad permissions | `chmod 400 landing/povver-rsa.pem` |
| `scp: failed to upload directory` | Remote temp dir missing (newer OpenSSH) | Already handled in deploy script via rsync |
| Changes not visible after deploy | Browser serving stale cached assets | Already handled — deploy script stamps `?v=<timestamp>` on all asset URLs |

## Launch Checklist

Before removing `noindex`:
- [x] Replace placeholder screenshot for Feature 1 (Activity with Auto-Pilot)
- [x] Replace `train.png` with a real phone screenshot
- [ ] Create `og-image.png` (1200x630) for social sharing
- [x] Set App Store badge `href` to actual App Store link (Apple ID: 6759248585)
- [x] Set Privacy Policy and Terms of Service links
- [x] Replace `G-XXXXXXXXXX` in `script.js` with actual GA4 measurement ID (`G-V9YHQNJTB7`)
- [ ] Set up `privacy@povver.ai` and `legal@povver.ai` email addresses
- [ ] Incorporate as Finnish Oy (update entity references in privacy.html and tos.html)
- [ ] Restrict App Store distribution to: EU, EEA, UK, US, Canada, Australia, NZ
- [ ] Remove `<meta name="robots" content="noindex, nofollow">` from all HTML files
- [ ] Remove `Disallow: /` from `robots.txt`
