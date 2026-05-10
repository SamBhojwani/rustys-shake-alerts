import { useState, useEffect } from 'react';
import { getSubscribers, deleteSubscriber } from '../api';

const STATUSES = ['', 'active', 'pending', 'unsubscribed', 'bounced'];

export default function Subscribers() {
  const [subscribers, setSubscribers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [nextKey, setNextKey] = useState(null);
  const [deleting, setDeleting] = useState('');

  async function load(status = statusFilter, startKey = '') {
    setLoading(true);
    setError('');
    try {
      const res = await getSubscribers(status, 25, startKey);
      if (startKey) {
        setSubscribers((prev) => [...prev, ...(res.subscribers || [])]);
      } else {
        setSubscribers(res.subscribers || []);
      }
      setNextKey(res.nextKey || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function handleFilterChange(status) {
    setStatusFilter(status);
    setNextKey(null);
    load(status, '');
  }

  async function handleDelete(email) {
    if (!confirm(`Remove ${email}? This cannot be undone.`)) return;
    setDeleting(email);
    try {
      await deleteSubscriber(email);
      setSubscribers((prev) => prev.filter((s) => s.email !== email));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting('');
    }
  }

  function handleExportCSV() {
    if (subscribers.length === 0) return;
    const headers = ['email', 'name', 'status', 'confirmed', 'subscribed_at'];
    const rows = subscribers.map((s) =>
      headers.map((h) => `"${String(s[h] ?? '').replace(/"/g, '""')}"`).join(',')
    );
    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `subscribers_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="page-header">
        <h2>Subscribers</h2>
        <p>Manage your subscriber list</p>
      </div>

      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {STATUSES.map((s) => (
              <button
                key={s}
                className={`btn btn-sm ${statusFilter === s ? 'btn-primary' : ''}`}
                onClick={() => handleFilterChange(s)}
              >
                {s || 'All'}
              </button>
            ))}
          </div>
          <button className="btn btn-sm" onClick={handleExportCSV} disabled={subscribers.length === 0}>
            📥 Export CSV
          </button>
        </div>

        {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

        <table className="data-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Status</th>
              <th>Confirmed</th>
              <th>Subscribed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {subscribers.map((s) => (
              <tr key={s.email}>
                <td>{s.email}</td>
                <td>{s.name || '—'}</td>
                <td>
                  <span className={`badge badge-${s.status}`}>{s.status}</span>
                </td>
                <td>{s.confirmed ? '✅' : '—'}</td>
                <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                  {s.subscribed_at ? new Date(s.subscribed_at).toLocaleDateString() : '—'}
                </td>
                <td>
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={() => handleDelete(s.email)}
                    disabled={deleting === s.email}
                  >
                    {deleting === s.email ? '…' : '🗑'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {loading && <div className="loading-center"><div className="spinner" /></div>}

        {!loading && subscribers.length === 0 && (
          <p style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)' }}>
            No subscribers found.
          </p>
        )}

        {nextKey && !loading && (
          <div style={{ textAlign: 'center', padding: 16 }}>
            <button className="btn" onClick={() => load(statusFilter, nextKey)}>
              Load More
            </button>
          </div>
        )}
      </div>
    </>
  );
}
