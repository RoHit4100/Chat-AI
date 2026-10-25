import Keycloak from "keycloak-js";

// Keycloak configuration for realm "chat" and public client "chat-web"
const keycloak = new Keycloak({
  url: "http://localhost:8080",
  realm: "chat",
  clientId: "chat-web",
});

let isInitialized = false;

// Handle session expiration by purging state and redirecting to login
export function handleAuthSessionExpired() {
  localStorage.clear();
  sessionStorage.clear();
  if (keycloak.authenticated) {
    keycloak.login({
      redirectUri: window.location.origin,
    });
  } else {
    window.location.reload();
  }
}

// Automatically handle token expiration and refresh errors
keycloak.onTokenExpired = () => {
  keycloak.updateToken(30).catch((err) => {
    console.warn("Keycloak token refresh failed on expiry:", err);
    handleAuthSessionExpired();
  });
};

keycloak.onAuthRefreshError = () => {
  console.warn("Keycloak onAuthRefreshError: refresh token invalid or revoked.");
  handleAuthSessionExpired();
};

export async function initAuth() {
  if (isInitialized) return keycloak.authenticated;

  try {
    const authenticated = await keycloak.init({
      onLoad: "login-required",
      pkceMethod: "S256",
      checkLoginIframe: false,
    });
    isInitialized = true;
    return authenticated;
  } catch (error) {
    console.warn("Keycloak initialization bypassed or unavailable (running in local mode):", error);
    isInitialized = true;
    return false;
  }
}

export async function getToken() {
  // If Keycloak is authenticated, ensure the token is refreshed and return it
  if (keycloak.authenticated) {
    try {
      await keycloak.updateToken(30);
      return keycloak.token;
    } catch (err) {
      console.warn("Failed to refresh Keycloak token (session expired):", err);
      handleAuthSessionExpired();
      return "";
    }
  }

  // Fallback to local storage or demo token for local development
  return localStorage.getItem("auth_token") || "";
}

export function login() {
  keycloak.login({
    redirectUri: window.location.origin,
  });
}

export function logout() {
  // Thoroughly clear all localStorage and sessionStorage to prevent cross-user thread bleed
  localStorage.clear();
  sessionStorage.clear();

  if (keycloak.authenticated) {
    keycloak.logout({
      redirectUri: window.location.origin,
    });
  } else {
    window.location.reload();
  }
}

export function getUserInfo() {
  if (keycloak.authenticated && keycloak.tokenParsed) {
    return {
      username: keycloak.tokenParsed.preferred_username || keycloak.tokenParsed.sub || "User",
      email: keycloak.tokenParsed.email || "",
    };
  }
  return null;
}

export { keycloak };
