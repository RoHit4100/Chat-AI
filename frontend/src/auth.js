import Keycloak from "keycloak-js";

// Keycloak configuration for realm "chat" and public client "chat-web"
const keycloak = new Keycloak({
  url: "http://localhost:8080",
  realm: "chat",
  clientId: "chat-web",
});

let isInitialized = false;

export async function initAuth() {
  if (isInitialized) return keycloak.authenticated;

  try {
    const authenticated = await keycloak.init({
      onLoad: "check-sso",
      pkceMethod: "S256",
      silentCheckSsoRedirectUri: window.location.origin + "/silent-check-sso.html",
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
      console.warn("Failed to refresh Keycloak token:", err);
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
  if (keycloak.authenticated) {
    keycloak.logout({
      redirectUri: window.location.origin,
    });
  } else {
    localStorage.removeItem("auth_token");
    window.location.reload();
  }
}

export function getUserInfo() {
  if (keycloak.tokenParsed) {
    return {
      username: keycloak.tokenParsed.preferred_username || keycloak.tokenParsed.sub || "User",
      email: keycloak.tokenParsed.email || "demo@example.com",
    };
  }
  return {
    username: "Demo User",
    email: "demo@example.com",
  };
}

export { keycloak };
