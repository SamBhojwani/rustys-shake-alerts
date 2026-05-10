import { useState, useEffect } from 'react';
import { getSubscriberStats } from '../api';
import { getGoals } from '../api';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recentGoals, setRecentGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const [statsRes, goalsRes] = await Promise.all([
          getSubscriberStats(),
          getGoals(5),
        ]);
        setStats(statsRes.stats);
        setRecentGoals(goalsRes.goals || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <div className="loading-center"><div className="spinner" /></div>;
  }

  if (error) {
    return <div className="card"><p className="error-msg">{error}</p></div>;
  }

  return (
    <>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Overview of your Rusty's Shake alert system</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats?.total ?? '—'}</div>
          <div className="stat-label">Total Subscribers</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.active ?? '—'}</div>
          <div className="stat-label">Active</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.pending ?? '—'}</div>
          <div className="stat-label">Pending</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.unsubscribed ?? '—'}</div>
          <div className="stat-label">Unsubscribed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.bounced ?? '—'}</div>
          <div className="stat-label">Bounced</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Recent Goal Events</h3>
        </div>
        {recentGoals.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>No goal events recorded yet.</p>
        ) : (
          recentGoals.map((g) => (
            <div className="goal-item" key={g.game_date}>
              <div className="goal-date">{g.game_date}</div>
              <div className="goal-detail">
                <span className="goals-count">{g.goals} goal{g.goals !== 1 ? 's' : ''}</span>
                {' '}vs {g.opponent}
                {g.emails_sent > 0 && (
                  <span style={{ color: 'var(--text-muted)', marginLeft: 12, fontSize: 13 }}>
                    📧 {g.emails_sent} email{g.emails_sent !== 1 ? 's' : ''} sent
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
