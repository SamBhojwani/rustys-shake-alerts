// ═══════════════════════════════════════════════════════════════════
// API Client — authenticated requests to the admin API
// ═══════════════════════════════════════════════════════════════════

import { getIdToken } from './auth';

const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

async function authFetch(path, options = {}) {
  const token = await getIdToken();

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });

  if (response.status === 401) {
    throw new Error('Unauthorized — please log in again.');
  }

  return response.json();
}

// ── Subscribers ────────────────────────────────────────────────────

export async function getSubscribers(status = '', limit = 25, startKey = '') {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (limit) params.set('limit', String(limit));
  if (startKey) params.set('startKey', startKey);

  const query = params.toString();
  return authFetch(`/admin/subscribers${query ? '?' + query : ''}`);
}

export async function getSubscriberStats() {
  return authFetch('/admin/subscribers/stats');
}

export async function deleteSubscriber(email) {
  return authFetch(`/admin/subscribers/${encodeURIComponent(email)}`, {
    method: 'DELETE',
  });
}

// ── Goals ──────────────────────────────────────────────────────────

export async function getGoals(limit = 50) {
  return authFetch(`/admin/goals?limit=${limit}`);
}

// ── Tools ──────────────────────────────────────────────────────────

export async function sendTestEmail() {
  return authFetch('/admin/test-email', { method: 'POST' });
}

export async function triggerGoalCheck() {
  return authFetch('/admin/trigger-check', { method: 'POST' });
}
