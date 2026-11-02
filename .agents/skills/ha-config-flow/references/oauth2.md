# OAuth2 setup with application credentials

For a cloud service that authenticates with OAuth2. Home Assistant owns the token dance; the integration only says
where the authorization server is and what to do once a token exists.

**New integrations must not accept credentials in `configuration.yaml`.** The user enters their client ID and secret
once, in Settings → Devices & Services → Application Credentials, and every config entry of this integration reuses
them.

## 1. Manifest

```json
"dependencies": ["application_credentials"]
```

## 2. `application_credentials.py`

At the integration root, beside `config_flow.py`:

```python
from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return the authorization server."""
    return AuthorizationServer(
        authorize_url="https://example.com/oauth2/authorize",
        token_url="https://example.com/oauth2/token",
    )
```

Both fields are plain strings and both are required. Two optional functions live in the same module:

| Function                                                       | Use it for                                                                                 |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `async_get_auth_implementation(hass, auth_domain, credential)` | A service that does not fit the plain implementation — PKCE, a non-standard token exchange |
| `async_get_description_placeholders(hass)`                     | Values for the `application_credentials.description` translation key                       |

For PKCE, return a `LocalOAuth2ImplementationWithPkce(hass, domain, client_id, authorize_url, token_url, client_secret="", code_verifier_length=128)`
from `async_get_auth_implementation`.

## 3. The flow

The handler inherits from `AbstractOAuth2FlowHandler`, which brings `async_step_user`, `async_step_pick_implementation`,
`async_step_auth` and `async_step_creation` with it. Two members are yours:

```python
from homeassistant.helpers import config_entry_oauth2_flow


class {ClassPrefix}ConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle OAuth2 authentication."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
        return LOGGER

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Create the entry from the token data."""
```

- `extra_authorize_data` adds query parameters to the authorize URL — this is where a `scope` goes.
- **Reauth** is `async_step_reauth` / `async_step_reauth_confirm` plus an `async_oauth_create_entry` that updates the
  existing entry instead of creating a second one. The base class does not do that for you.
- The token dict is stored under `entry.data["token"]`. Do not reshape it; the helper refreshes it in place.

## 4. Setting up the entry

In `async_setup_entry`, resolve the implementation and hand an `OAuth2Session` to the client:

```python
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)


async def async_setup_entry(hass: HomeAssistant, entry: {ClassPrefix}ConfigEntry) -> bool:
    """Set up from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    session = OAuth2Session(hass, entry, implementation)
    coordinator = {ClassPrefix}DataUpdateCoordinator(hass, entry, {ClassPrefix}ApiClient(session))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
```

The client calls `await session.async_ensure_token_valid()` before each request and reads
`session.token["access_token"]`.

**Map OAuth2 failures for Home Assistant 2026.8.0.**

On this baseline, resolving an unavailable implementation can raise `ValueError`, and token-refresh failures are
not all config-entry exceptions. Handle failures where the client is set up: map missing/invalid credentials and
HTTP 401/403 to `ConfigEntryAuthFailed`, and timeouts, connection failures, or temporary service errors to
`ConfigEntryNotReady`. Do not catch these broadly and turn invalid credentials into an endless retry.

Newer central OAuth2 exception mapping must not be assumed on 2026.8. Verify the installed helper's actual exception
classes before choosing catches; do not import newer `OAuth2TokenRequest*Error` classes into this baseline.

## 5. Translations

Beyond the usual `config.*` keys, the application-credentials dialog reads a top-level key that tells the user where
to get a client ID:

```json
"application_credentials": {
  "description": "Create a client ID and secret at {more_info_url}, then enter them here."
}
```

Placeholders come from `async_get_description_placeholders(hass)`. The field renders Markdown, so a real link works
here too.

## Do not

- Do not create your own aiohttp session or refresh the token by hand — `OAuth2Session` does both.
- Do not put the client secret in `entry.data`. It belongs to the application credential, not to the entry.
- Do not add an options flow field for the token.
