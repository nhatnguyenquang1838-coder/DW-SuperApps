#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ZSHRC="$HOME/.zshrc"
ENV_FILE="$ROOT_DIR/.env.gg-oauth"
ENV_FILE_PHYSICAL="$ROOT_DIR/gg-oauth-env.txt"

cat > "$ENV_FILE" << 'ENVEOF'
# GG OAuth Configuration for dw-super-chatgpt-app-complete-v1
# Vercel Project: dw-super-chatgpt-app-complete-v1
# Vercel Project ID: prj_OY5gKUjORdSOwHfdGFGb7kDs7u1S
# Vercel Team: DW1407 (team_4mKlLmlLe2pWbK5F5e10zck1)
#
# Copy these values into Vercel -> Project -> Settings -> Environment Variables.
# Separate Preview and Production values where noted.

# OAuth Provider Endpoints
GG_OAUTH_AUTHORIZATION_URL="https://supabase.com/auth/v1/authorize"
GG_OAUTH_TOKEN_URL="https://supabase.com/auth/v1/token"
GG_OAUTH_REVOCATION_URL="https://supabase.com/auth/v1/logout"

# OAuth Credentials (create these in your Supabase / Vercel OAuth app dashboard)
GG_OAUTH_CLIENT_ID="<PLACEHOLDER_CLIENT_ID>"
GG_OAUTH_CLIENT_SECRET="<PLACEHOLDER_CLIENT_SECRET>"

# OAuth Scopes and Redirect
GG_OAUTH_SCOPES="openid email profile offline_access"
GG_OAUTH_REDIRECT_URI="https://dw-super-chatgpt-app-complete-v1-nnv7mi9qe-dw1407.vercel.app/api/auth/gg/callback"

# Supabase Project (used for callback session exchange)
NEXT_PUBLIC_SUPABASE_URL="<PLACEHOLDER_SUPABASE_URL>"
NEXT_PUBLIC_SUPABASE_ANON_KEY="<PLACEHOLDER_SUPABASE_ANON_KEY>"
SUPABASE_SERVICE_ROLE_KEY="<PLACEHOLDER_SUPABASE_SERVICE_ROLE_KEY>"

# App Base URL
APP_BASE_URL="https://dw-super-chatgpt-app-complete-v1-nnv7mi9qe-dw1407.vercel.app"

# Session / Token Security
SESSION_SECRET="<PLACEHOLDER_SESSION_SECRET>"
TOKEN_ENCRYPTION_KEY="<PLACEHOLDER_TOKEN_ENCRYPTION_KEY>"
ENVEOF

cat > "$ENV_FILE_PHYSICAL" << 'PHYEOF'
================================================================================
GG OAuth Environment Variables — dw-super-chatgpt-app-complete-v1
Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
================================================================================

Vercel Project:     dw-super-chatgpt-app-complete-v1
Vercel Project ID:  prj_OY5gKUjORdSOwHfdGFGb7kDs7u1S
Vercel Team:        DW1407 (team_4mKlLmlLe2pWbK5F5e10zck1)

--------------------------------------------------------------------------------
1. Copy values below into Vercel -> Project -> Settings -> Environment Variables
--------------------------------------------------------------------------------

GG_OAUTH_AUTHORIZATION_URL="https://supabase.com/auth/v1/authorize"
GG_OAUTH_TOKEN_URL="https://supabase.com/auth/v1/token"
GG_OAUTH_REVOCATION_URL="https://supabase.com/auth/v1/logout"
GG_OAUTH_CLIENT_ID="<REPLACE_WITH_YOUR_CLIENT_ID>"
GG_OAUTH_CLIENT_SECRET="<REPLACE_WITH_YOUR_CLIENT_SECRET>"
GG_OAUTH_SCOPES="openid email profile offline_access"
GG_OAUTH_REDIRECT_URI="https://dw-super-chatgpt-app-complete-v1-nnv7mi9qe-dw1407.vercel.app/api/auth/gg/callback"
NEXT_PUBLIC_SUPABASE_URL="<REPLACE_WITH_YOUR_SUPABASE_URL>"
NEXT_PUBLIC_SUPABASE_ANON_KEY="<REPLACE_WITH_YOUR_SUPABASE_ANON_KEY>"
SUPABASE_SERVICE_ROLE_KEY="<REPLACE_WITH_YOUR_SUPABASE_SERVICE_ROLE_KEY>"
APP_BASE_URL="https://dw-super-chatgpt-app-complete-v1-nnv7mi9qe-dw1407.vercel.app"
SESSION_SECRET="<REPLACE_WITH_YOUR_SESSION_SECRET>"
TOKEN_ENCRYPTION_KEY="<REPLACE_WITH_YOUR_TOKEN_ENCRYPTION_KEY>"

--------------------------------------------------------------------------------
2. Preview Deployment Redirect Policy
--------------------------------------------------------------------------------

Option A (recommended): Register a fixed preview OAuth callback domain.
Option B: Disable OAuth on arbitrary preview URLs.
Option C: Use separate OAuth clients for Preview and Production.

Production callback:
  https://dw-super-chatgpt-app-complete-v1-nnv7mi9qe-dw1407.vercel.app/api/auth/gg/callback

Preview callback:
  https://dw-super-chatgpt-app-complete-v1-<preview-id>.vercel.app/api/auth/gg/callback

--------------------------------------------------------------------------------
3. Security Notes
--------------------------------------------------------------------------------

- Never commit secrets to version control.
- .env.gg-oauth is listed in .gitignore.
- gg-oauth-env.txt is a physical reference file; keep it in a secure location.
- Separate Preview and Production values in Vercel dashboard.
- Bind the production redirect URI exactly; do not use wildcards.
================================================================================
PHYEOF

# Append to .zshrc if not already present
if [ -f "$ZSHRC" ]; then
  if ! grep -q "GG_OAUTH_CLIENT_ID" "$ZSHRC" 2>/dev/null; then
    echo "" >> "$ZSHRC"
    echo "# GG OAuth environment for dw-super-chatgpt-app" >> "$ZSHRC"
    echo "source $ENV_FILE" >> "$ZSHRC"
    echo "GG OAuth env sourced in .zshrc"
  else
    echo "GG OAuth env already present in .zshrc"
  fi
else
  echo "# GG OAuth environment for dw-super-chatgpt-app" > "$ZSHRC"
  echo "source $ENV_FILE" >> "$ZSHRC"
  echo "Created .zshrc and sourced GG OAuth env"
fi

echo ""
echo "=== Generated files ==="
echo "Env file (sourceable): $ENV_FILE"
echo "Physical reference:    $ENV_FILE_PHYSICAL"
echo "Zshrc updated:         $ZSHRC"
echo ""
echo "=== Next steps ==="
echo "1. Replace <PLACEHOLDER_> values with real credentials"
echo "2. Set values in Vercel dashboard (Settings -> Environment Variables)"
echo "3. Register redirect URIs in your OAuth provider"
echo "4. Restart your shell: exec zsh"