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
├── index.html               # Single-page landing (SEO meta, OG, JSON-LD)
├── styles.css               # All styles — mobile-first, CSS custom properties
├── script.js                # Scroll animations, mobile nav, smooth scroll (~95 lines)
├── deploy.sh                # SCP deploy to EC2 instance
├── robots.txt               # Disallow all (staging — remove for launch)
└── assets/
    ├── favicon.svg           # SVG favicon (emerald "P")
    ├── statusbar.svg         # iOS status bar overlay (unused — real screenshots have it)
    └── screenshots/          # App screenshots (iPhone, 520px wide for 2x Retina)
        ├── coach.png         # Hero: Coach tab home screen
        ├── plan.png          # Feature 2: AI-generated workout plan
        ├── grid.png          # Feature 3: Set logging grid
        ├── train.png         # Feature 4: Train tab (old simulator screenshot, uses contain)
        └── workout.png       # Currently unused (keyboard-open grid)
```

## Design Decisions

**Mobile-first CSS**: Base styles target mobile (375px). Desktop layout scales up via `@media (min-width: 768px)`. Design tokens in `:root` use mobile values; the `min-width` media query overrides them for desktop (nav height, section padding, container padding).

**Brand tokens**: Sourced from the iOS app's `Tokens.swift` and color assets. Accent emerald `#0B7A5E`, dark background `#0C1117`, system font stack.

**Phone mockups**: On desktop, screenshots render inside a dark device frame (40px border-radius, 6px padding). On mobile, the frame is stripped and screenshots show as clean rounded images to reduce visual weight and scrolling.

**Hero on mobile**: Phone mockup is hidden. Text-only hero with centered layout to maximize the headline-to-CTA distance.

**No build step**: The page is three files (HTML, CSS, JS) deployed directly. Cache busting via `?v=N` query string on the CSS link.

## Page Sections

1. **Nav** — Fixed, transparent over dark hero, frosted glass when scrolled past hero
2. **Hero** — Dark background with ambient emerald glow, animated gradient accent text, phone mockup (desktop only)
3. **Features** (x4) — Alternating left/right layout on desktop, stacked on mobile
4. **Highlights** — Single-line emerald gradient strip
5. **Final CTA** — Dark background with centered glow, App Store badge
6. **Footer** — Dark, minimal

## Deployment

```bash
cd landing
./deploy.sh
```

Requires SSH access to the EC2 instance. The PEM key is not in the repo (gitignored).

## Launch Checklist

Before removing `noindex`:
- [ ] Replace placeholder screenshot for Feature 1 (post-workout analysis)
- [ ] Replace `train.png` with a real phone screenshot
- [ ] Create `og-image.png` (1200x630) for social sharing
- [ ] Set App Store badge `href` to actual App Store link
- [ ] Set Privacy Policy and Terms of Service links
- [ ] Remove `<meta name="robots" content="noindex, nofollow">` from `index.html`
- [ ] Remove `Disallow: /` from `robots.txt`
