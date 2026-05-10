// ═══════════════════════════════════════════════════════════════════
// Cognito Auth Module — handles login, token management, and session
// ═══════════════════════════════════════════════════════════════════

// ── Config ─────────────────────────────────────────────────────────
// These are PUBLIC identifiers — not secrets.
// Auth is validated server-side via JWT verification.
const POOL_CONFIG = {
  UserPoolId: import.meta.env.VITE_USER_POOL_ID || '',
  ClientId: import.meta.env.VITE_CLIENT_ID || '',
};

const IS_CONFIGURED = Boolean(POOL_CONFIG.UserPoolId && POOL_CONFIG.ClientId);

// Lazy-load the Cognito library to avoid import-time errors
let CognitoUserPool, CognitoUser, AuthenticationDetails;
let cognitoLoaded = false;

async function loadCognito() {
  if (cognitoLoaded) return;
  try {
    const mod = await import('amazon-cognito-identity-js');
    CognitoUserPool = mod.CognitoUserPool;
    CognitoUser = mod.CognitoUser;
    AuthenticationDetails = mod.AuthenticationDetails;
    cognitoLoaded = true;
  } catch (err) {
    console.warn('Failed to load Cognito library:', err);
  }
}

let userPool = null;

function getPool() {
  if (!IS_CONFIGURED || !cognitoLoaded) return null;
  if (!userPool) {
    userPool = new CognitoUserPool(POOL_CONFIG);
  }
  return userPool;
}

// ── Login ──────────────────────────────────────────────────────────

export async function login(email, password) {
  await loadCognito();
  const pool = getPool();
  if (!pool) {
    throw new Error('Auth not configured. Set VITE_USER_POOL_ID and VITE_CLIENT_ID.');
  }

  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool });
    const authDetails = new AuthenticationDetails({
      Username: email,
      Password: password,
    });

    user.authenticateUser(authDetails, {
      onSuccess: (session) => {
        resolve({ session, newPasswordRequired: false });
      },
      onFailure: (err) => {
        reject(err);
      },
      newPasswordRequired: (userAttributes) => {
        resolve({ user, newPasswordRequired: true, userAttributes });
      },
    });
  });
}

// ── Complete New Password Challenge ────────────────────────────────

export function completeNewPassword(user, newPassword) {
  return new Promise((resolve, reject) => {
    user.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess: (session) => resolve(session),
      onFailure: (err) => reject(err),
    });
  });
}

// ── Get Current Session ────────────────────────────────────────────

export async function getSession() {
  await loadCognito();
  const pool = getPool();
  if (!pool) throw new Error('Auth not configured.');

  return new Promise((resolve, reject) => {
    const user = pool.getCurrentUser();
    if (!user) {
      reject(new Error('Not logged in.'));
      return;
    }

    user.getSession((err, session) => {
      if (err) {
        reject(err);
      } else if (!session.isValid()) {
        reject(new Error('Session expired.'));
      } else {
        resolve(session);
      }
    });
  });
}

// ── Get ID Token (for API calls) ──────────────────────────────────

export async function getIdToken() {
  const session = await getSession();
  return session.getIdToken().getJwtToken();
}

// ── Get Admin Email ────────────────────────────────────────────────

export async function getAdminEmail() {
  const session = await getSession();
  return session.getIdToken().payload.email || 'admin';
}

// ── Logout ─────────────────────────────────────────────────────────

export function logout() {
  const pool = getPool();
  if (pool) {
    const user = pool.getCurrentUser();
    if (user) {
      user.signOut();
    }
  }
}

// ── Check if Logged In ─────────────────────────────────────────────

export async function isAuthenticated() {
  if (!IS_CONFIGURED) return false;
  try {
    await getSession();
    return true;
  } catch {
    return false;
  }
}
