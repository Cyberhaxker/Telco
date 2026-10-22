// Silent-renew callback for oidc-client-ts: hand the authorization response URL
// back to the app window (same message format as UserManager.signinSilentCallback).
window.parent.postMessage({ source: "oidc-client", url: window.location.href, keepOpen: false }, window.location.origin);
