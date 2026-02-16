# Apple Root Certificates

This directory should contain Apple's root certificates for JWS verification.

## Required Certificates

Download these from https://www.apple.com/certificateauthority/:

1. **AppleRootCA-G3.cer** - Apple Root CA - G3 Root
2. **AppleRootCA-G2.cer** - Apple Root CA - G2 Root

## Installation

1. Download the .cer files from Apple's PKI site
2. Place them in this directory
3. Update the app-store-webhook.js to use SignedDataVerifier with these certificates

## Security Note

The .cer files should NOT be committed to the repository. This directory is for deployment only.
