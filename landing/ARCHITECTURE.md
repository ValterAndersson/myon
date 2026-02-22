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

**Brand tokens**: Accent green `#22C59A`, dark background `#0A0E14`, Inter font via Google Fonts with system fallback. Full token set in `:root` CSS custom properties.

**Phone mockups**: On desktop, screenshots render inside a dark device frame (42px border-radius, 6px padding, 280px wide) with a floating bob animation and radial glow. On mobile, device frames are 220px with a smaller glow, no float animation.

**Hero on mobile**: Phone mockup is hidden to avoid back-to-back phones with the first feature screenshot. Text-only hero with centered layout: label pill, headline, subtitle, App Store button, scroll cue.

**Feature numbering**: Each feature section has an `01`–`04` accent-colored number label above the title for visual progression.

**Staggered scroll animations**: Feature screenshots animate in first via IntersectionObserver; text content follows with a 150ms delay. Highlight stats cascade in sequentially with 100ms offsets.

**Scroll cue**: A pulsing green dot with a gradient line at the bottom of the hero. Fades out via JS after 80px of scroll.

**Grain texture**: A subtle SVG noise overlay (`opacity: 0.02`) fixed over the entire viewport for tactile depth.

**No build step**: The page is three files (HTML, CSS, JS) deployed directly. Cache busting via `?v=N` query string on the CSS link.

## Page Sections

1. **Nav** — Fixed, transparent over dark hero, glassmorphic (`backdrop-filter: blur(20px)`) when scrolled past hero
2. **Hero** — Mesh gradient background (multiple radial gradients), animated gradient accent text, phone mockup (desktop only), scroll cue
3. **Features** (x4) — Alternating left/right layout on desktop. On mobile, screenshots shown first (`order: -1`), then text. Numbered 01–04. Gradient dividers between sections, alternating subtle backgrounds
4. **Highlights** — 3-column stat grid (900+, Every, Free) with gradient text values and vertical dividers
5. **Final CTA** — Centered radial glow, accent gradient divider at top
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
