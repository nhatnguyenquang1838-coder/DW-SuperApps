# Implementation Plan: Change `@GG` Authentication to OAuth

## 1. Executive Summary

This plan outlines the end-to-end implementation for transitioning the `@GG` (GitHub / Governance Gateway) integration in the DW ChatGPT application (`dw-super-chatgpt-app-complete-v1`) from static personal access tokens to a secure, robust OAuth 2.0 authentication flow with PKCE, server-side session management, automatic token refresh, token revocation, and secure authorization boundaries.

---

## 2. Core Architecture & Endpoints

### 2.1 OAuth Authorization Start (`GET /api/auth/gg/authorize`)
- **Parameters / Query:** Optional return path (`returnTo`).
- **Logic:**
  1. Generate a cryptographically secure random `state` parameter (stored in a short-lived HTTP-only cookie with `SameSite=Lax`).
  2. Generate PKCE `code_verifier` and compute `code_challenge` (SHA-256) if the OAuth provider supports PKCE.
  3. Construct the provider authorization URL using configured environment variables (`GG_OAUTH_AUTHORIZATION_URL`, `GG_OAUTH_CLIENT_ID`, `GG_OAUTH_REDIRECT_URI`, `GG_OAUTH_SCOPES`, `code_challenge`, `state`).
  4. Redirect the user securely (`302 Found`).

### 2.2 OAuth Callback (`GET /api/auth/gg/callback`)
- **Query Parameters:** `code`, `state`, `error`, `error_description`.
- **Logic:**
  1. Validate incoming `state` against the stored state cookie. Reject immediately if mismatch or expired (CSRF protection).
  2. Handle provider denial or error query params gracefully.
  3. Exchange authorization code and PKCE `code_verifier` for tokens at `GG_OAUTH_TOKEN_URL`.
  4. Validate token response structure (access token, refresh token, expiry, scopes).
  5. Establish secure server-side session mapping user identity and encrypted tokens.
  6. Clear temporary state cookies and redirect to the application UI / return path.

### 2.3 Session & Token Storage
- **Storage Strategy:** Server-side secure session store backed by encrypted session cookies (`SESSION_SECRET`) or secure in-memory/database session vaults.
- **Token Protection:** Access and refresh tokens are encrypted at rest using `TOKEN_ENCRYPTION_KEY`. Raw tokens are never exposed to the client/frontend.
- **Session Attributes:**
  - `sessionId`
  - `providerUserId`
  - `workspaceId`
  - `scopes`
  - `accessToken` (encrypted)
  - `refreshToken` (encrypted)
  - `expiresAt`
  - `createdAt`

### 2.4 Token Refresh Mechanism
- Automatically check access token expiry before making requests to GG APIs.
- If expired or expiring within 60 seconds, use the refresh token against `GG_OAUTH_TOKEN_URL`.
- Handle concurrent refresh requests safely (mutex/serialization).
- Handle token rotation (updating stored refresh tokens if the provider rotates them).
- Invalidate session if refresh fails permanently (e.g. revoked authorization).

### 2.5 GG Request Authentication (`callGG`)
- Update `callGG` (in `src/server.ts` or modular client) to retrieve the active session's decrypted OAuth access token.
- Ensure proper error classification: `UNAUTHENTICATED`, `TOKEN_EXPIRED`, `INSUFFICIENT_SCOPE`, `PROVIDER_UNAVAILABLE`, `GG_API_FAILED`.

### 2.6 Logout & Revocation (`POST /api/auth/gg/logout`)
- Invalidate local session.
- Invoke provider revocation endpoint (`GG_OAUTH_REVOCATION_URL`) if supported.
- Clear authentication cookies.
- Redirect to signed-out state.

### 2.7 Session Status Endpoint (`GET /api/auth/gg/session`)
- Returns safe session metadata (authenticated status, display name, scopes, expiry) without exposing raw tokens.

---

## 3. Environment Variables

Required production & preview environment variables:
- `GG_OAUTH_CLIENT_ID`
- `GG_OAUTH_CLIENT_SECRET`
- `GG_OAUTH_AUTHORIZATION_URL`
- `GG_OAUTH_TOKEN_URL`
- `GG_OAUTH_REVOCATION_URL`
- `GG_OAUTH_SCOPES`
- `GG_OAUTH_REDIRECT_URI`
- `SESSION_SECRET`
- `TOKEN_ENCRYPTION_KEY`
- `APP_BASE_URL`

---

## 4. UI & State Management

- Implement clear UI states in the widget / cockpit:
  - **Connect GG** (initiates `/api/auth/gg/authorize`)
  - **GG Connected** (displays status, user info, scope summary)
  - **Reconnect / Re-authenticate** (triggered upon session expiry or insufficient scope)
  - **Disconnect GG** (triggers `/api/auth/gg/logout`)
- Prevent false connected states on authorization failure.

---

## 5. Security Acceptance Criteria

- [ ] CSRF state validation on callbacks.
- [ ] PKCE implemented and verified.
- [ ] Redirect URI allowlisting enforced.
- [ ] Tokens stored server-side only; never sent to frontend.
- [ ] Cookies configured with `Secure`, `HttpOnly`, and explicit `SameSite`.
- [ ] Refresh token rotation and permanent failure handling.
- [ ] Separation of authentication and GG authorization boundaries.
- [ ] Zero secrets or tokens in logs or error payloads.

---

## 6. Testing & Validation Plan

### 6.1 Unit Tests
- State generation and verification.
- PKCE challenge generation.
- Token response parsing and validation.
- Session serialization and encryption/decryption.
- Scope validation logic.

### 6.2 Integration Tests
- Successful authorization redirect and callback flow.
- Handling of provider denial and error states.
- Token refresh workflow and concurrency handling.
- Logout and token revocation.

### 6.3 Security Tests
- CSRF attack simulation (tampered/missing state).
- Callback replay protection.
- Open redirect vulnerability testing.
- Cross-user session isolation.

---

## 7. Execution & Delivery Roadmap

1. **Materialize Source & Setup Branch:** Ensure full repo access under `projects/dw-chatgpt-app` and create a dedicated feature branch.
2. **Implement Backend Endpoints:** Build `/authorize`, `/callback`, `/session`, and `/logout` routes with crypto utilities (state, PKCE, encryption).
3. **Integrate Token Refresh & GG Client:** Update `callGG` to use OAuth session tokens with automatic refresh handling.
4. **Update Frontend UI:** Add connection management buttons, status indicators, and error banners in the cockpit widget.
5. **Run Verification & Tests:** Execute unit/integration tests and verify build / type checking (`npm run build`, `npm test`).
6. **Open Draft PR:** Push changes and open a Draft PR for review.
