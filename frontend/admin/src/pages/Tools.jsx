import { useState } from 'react';
import { sendTestEmail, triggerGoalCheck } from '../api';

export default function Tools() {
  const [testStatus, setTestStatus] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [triggerStatus, setTriggerStatus] = useState('');
  const [triggerLoading, setTriggerLoading] = useState(false);

  async function handleTestEmail() {
    setTestLoading(true);
    setTestStatus('');
    try {
      const res = await sendTestEmail();
      setTestStatus(res.message || 'Test email sent!');
    } catch (err) {
      setTestStatus('Error: ' + (err.message || 'Failed'));
    } finally {
      setTestLoading(false);
    }
  }

  async function handleTrigger() {
    setTriggerLoading(true);
    setTriggerStatus('');
    try {
      const res = await triggerGoalCheck();
      setTriggerStatus(res.message || 'Goal check triggered!');
    } catch (err) {
      setTriggerStatus('Error: ' + (err.message || 'Failed'));
    } finally {
      setTriggerLoading(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h2>Tools</h2>
        <p>Admin utilities for testing and manual operations</p>
      </div>

      <div className="tools-grid">
        <div className="tool-card">
          <h3>📧 Send Test Email</h3>
          <p>
            Send a test goal alert email to your admin address.
            Useful for verifying email delivery and template rendering.
          </p>
          <button
            className="btn btn-primary"
            onClick={handleTestEmail}
            disabled={testLoading}
          >
            {testLoading ? 'Sending…' : 'Send Test Email'}
          </button>
          {testStatus && (
            <p className={testStatus.startsWith('Error') ? 'error-msg' : 'success-msg'}>
              {testStatus}
            </p>
          )}
        </div>

        <div className="tool-card">
          <h3>🏒 Manual Goal Check</h3>
          <p>
            Manually trigger the goal checker Lambda.
            It will check yesterday's games and send alerts if Rust scored.
          </p>
          <button
            className="btn btn-primary"
            onClick={handleTrigger}
            disabled={triggerLoading}
          >
            {triggerLoading ? 'Triggering…' : 'Trigger Goal Check'}
          </button>
          {triggerStatus && (
            <p className={triggerStatus.startsWith('Error') ? 'error-msg' : 'success-msg'}>
              {triggerStatus}
            </p>
          )}
        </div>
      </div>
    </>
  );
}
